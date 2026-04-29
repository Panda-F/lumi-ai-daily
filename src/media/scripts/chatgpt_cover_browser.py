#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from gemini_cover_browser import (
    DEFAULT_OPENCLAW_CDP_ENDPOINT,
    AttemptRecord,
    DOWNLOADS_ROOT,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    RunResult,
    SUPPORTED_IMAGE_SUFFIXES,
    UPLOADS_ROOT,
    capture_attempt_artifacts,
    first_working_action,
    launch_browser_context,
    load_manifest_assets,
    regex_for_names,
    require_visible,
    resolve_chrome_path,
    resolve_user_data_dir,
    result_to_dict,
    safe_visible_text,
    stage_assets,
    sync_playwright,
    validate_assets,
    wait_until,
    write_json,
)

os.environ.setdefault("NODE_NO_WARNINGS", "1")


CHATGPT_IMAGES_URL = "https://chatgpt.com/images"
CHATGPT_DEFAULT_OUTPUT_PREFIX = "chatgpt-cover"


class ChatGPTCoverError(RuntimeError):
    def __init__(
        self,
        stage: str,
        message: str,
        *,
        login_required: bool = False,
        selector_path: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.login_required = login_required
        self.selector_path = selector_path or []
        self.attempt_record: AttemptRecord | None = None


def derive_output_path(date_value: str) -> Path:
    safe_date = re.sub(r"[^0-9-]+", "-", date_value).strip("-") or "latest"
    return DOWNLOADS_ROOT / f"{CHATGPT_DEFAULT_OUTPUT_PREFIX}-{safe_date}.png"


def derive_result_path(output_path: Path) -> Path:
    return output_path.with_suffix(".result.json")


def derive_diagnostics_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}.diagnostics"


def ensure_logged_in(page: Page, attempt: AttemptRecord) -> None:
    if re.search(r"/auth|/login|/signup", page.url, re.IGNORECASE):
        raise ChatGPTCoverError("login_required", f"ChatGPT redirected to a login page: {page.url}", login_required=True)

    login_markers = [
        r"登录",
        r"Log in",
        r"Sign up",
        r"Continue with Google",
        r"Continue with Apple",
    ]
    for marker in login_markers:
        locator = page.get_by_text(re.compile(marker, re.IGNORECASE))
        try:
            if locator.first.is_visible(timeout=1200):
                raise ChatGPTCoverError(
                    "login_required",
                    f"ChatGPT appears to require login: {marker}",
                    login_required=True,
                    selector_path=attempt.selector_path,
                )
        except PlaywrightTimeoutError:
            continue
        except PlaywrightError:
            continue


def maybe_select_high_quality(page: Page, attempt: AttemptRecord) -> None:
    fast_button = page.get_by_role("button", name=regex_for_names(["快速", "Fast"])).first
    try:
        if not fast_button.is_visible(timeout=1200):
            return
    except PlaywrightError:
        return

    attempt.selector_path.append("button:快速|Fast")
    try:
        fast_button.click(timeout=3000)
        pro_option = page.get_by_text(regex_for_names(["进阶专业", "Pro", "高质量"])).first
        require_visible(pro_option, timeout=4000)
        pro_option.click(timeout=3000)
        page.wait_for_timeout(800)
    except PlaywrightError:
        # Quality selection is a best-effort nicety; failure should not block generation.
        return


def upload_ready(page: Page) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except PlaywrightError:
        body_text = ""
    if "我的图片" in body_text or "My image" in body_text:
        return True
    try:
        return page.locator("button[aria-label*='编辑图片'], button[aria-label*='Edit image']").count() > 0
    except PlaywrightError:
        return False


def upload_assets(page: Page, attempt: AttemptRecord, staged_files: list[Path]) -> None:
    str_paths = [str(path) for path in staged_files]

    def try_dom_file_input() -> bool:
        inputs = page.locator("input[type='file']")
        count = inputs.count()
        for idx in range(count):
            attempt.selector_path.append(f"input[type=file]:{idx}")
            try:
                inputs.nth(idx).set_input_files(str_paths, timeout=4000)
                return True
            except PlaywrightError:
                continue
        return False

    if not try_dom_file_input():
        chooser_candidates = [
            (
                "button:添加文件等|Add photos and files",
                lambda: require_visible(
                    page.get_by_role(
                        "button",
                        name=regex_for_names(["添加文件等", "Add photos and files", "Add files"]),
                    ).first
                ),
            ),
            (
                "button:Choose File",
                lambda: require_visible(page.get_by_role("button", name=regex_for_names(["Choose File"])).first),
            ),
        ]
        label, locator = first_working_action(
            attempt,
            chooser_candidates,
            stage="upload_picker",
            error_message="could not find the ChatGPT upload file action",
        )
        with page.expect_file_chooser(timeout=8000) as chooser_info:
            locator.click(timeout=5000)
        attempt.selector_path.append(f"file_chooser:{label}")
        chooser_info.value.set_files(str_paths)

    if not wait_until(lambda: upload_ready(page), timeout_s=25, interval_s=1.0):
        raise ChatGPTCoverError(
            "upload_wait",
            "ChatGPT did not show the uploaded image strip in time",
            selector_path=attempt.selector_path,
        )


def fill_prompt(page: Page, attempt: AttemptRecord, prompt: str) -> None:
    textbox_candidates = [
        (
            "textbox:描述新图片|Describe a new image|与 ChatGPT 聊天",
            lambda: require_visible(
                page.get_by_role(
                    "textbox",
                    name=regex_for_names(["描述新图片", "Describe a new image", "与 ChatGPT 聊天", "Message ChatGPT"]),
                ).first
            ),
        ),
        (
            "textarea",
            lambda: require_visible(page.locator("textarea").last),
        ),
        (
            "contenteditable:true",
            lambda: require_visible(page.locator("[contenteditable='true']").last),
        ),
    ]
    _label, textbox = first_working_action(
        attempt,
        textbox_candidates,
        stage="prompt_box",
        error_message="could not find the ChatGPT prompt composer",
    )
    textbox.click(timeout=5000)
    try:
        textbox.fill("", timeout=2000)
    except PlaywrightError:
        pass
    page.keyboard.insert_text(prompt)


def send_prompt(page: Page, attempt: AttemptRecord) -> None:
    send_button = page.get_by_role("button", name=regex_for_names(["发送提示", "Send prompt", "Send"])).first
    attempt.selector_path.append("button:发送提示|Send prompt|Send")
    try:
        send_button.wait_for(state="visible", timeout=5000)
    except PlaywrightError as exc:
        raise ChatGPTCoverError("send_prompt", f"could not find the ChatGPT send button: {exc}", selector_path=attempt.selector_path)

    if not wait_until(lambda: send_button.is_enabled(), timeout_s=15, interval_s=0.5):
        raise ChatGPTCoverError("send_prompt", "ChatGPT send button never became enabled", selector_path=attempt.selector_path)

    try:
        send_button.click(timeout=5000)
    except PlaywrightError as exc:
        raise ChatGPTCoverError("send_prompt", f"could not submit the ChatGPT prompt: {exc}", selector_path=attempt.selector_path)


def generated_image_candidates(page: Page) -> list[dict[str, Any]]:
    try:
        payload = page.evaluate(
            """() => Array.from(document.images)
                .map((img, index) => ({
                  index,
                  alt: img.alt || "",
                  src: img.src || "",
                  width: img.naturalWidth || 0,
                  height: img.naturalHeight || 0
                }))
                .filter(item => /已生成图片|Generated image/i.test(item.alt) && item.src && item.width >= 1000)"""
        )
    except PlaywrightError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def wait_for_generated_image(page: Page, attempt: AttemptRecord, known_srcs: set[str]) -> dict[str, Any]:
    def find_new_candidate() -> dict[str, Any] | None:
        for candidate in generated_image_candidates(page):
            src = str(candidate.get("src") or "")
            if src and src not in known_srcs:
                return candidate
        return None

    candidate: dict[str, Any] | None = None
    deadline_s = 240
    started = None
    while deadline_s > 0:
        body_text = safe_visible_text(page)
        if re.search(r"something went wrong|出现错误|出错了|出了点问题", body_text, re.IGNORECASE):
            raise ChatGPTCoverError("wait_for_image", f"ChatGPT returned an error while generating the cover: {body_text[:240]}")
        candidate = find_new_candidate()
        if candidate is not None:
            started = started or candidate.get("src")
            page.wait_for_timeout(1500)
            refreshed = find_new_candidate()
            if refreshed and refreshed.get("src") == started:
                return refreshed
        page.wait_for_timeout(2000)
        deadline_s -= 2

    raise ChatGPTCoverError("wait_for_image", "ChatGPT did not render a generated cover image in time", selector_path=attempt.selector_path)


def guess_suffix_from_response(content_type: str | None, body: bytes) -> str:
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type == "image/png" or body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content_type in {"image/jpeg", "image/jpg"} or body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content_type == "image/webp" or body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def download_generated_image(page: Page, attempt: AttemptRecord, image_url: str, output_path: Path) -> Path:
    try:
        response = page.context.request.get(image_url, timeout=30000)
    except PlaywrightError as exc:
        raise ChatGPTCoverError("download_image", f"could not fetch the ChatGPT image URL: {exc}", selector_path=attempt.selector_path)
    if not response.ok:
        raise ChatGPTCoverError(
            "download_image",
            f"ChatGPT image download returned HTTP {response.status}",
            selector_path=attempt.selector_path,
        )

    body = response.body()
    if not body:
        raise ChatGPTCoverError("download_image", "ChatGPT image response body was empty", selector_path=attempt.selector_path)

    suffix = guess_suffix_from_response(response.headers.get("content-type"), body)
    final_path = output_path.with_suffix(suffix)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(body)
    if final_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ChatGPTCoverError("download_image", f"unexpected image suffix: {final_path.suffix}", selector_path=attempt.selector_path)
    return final_path


def run_attempt(
    page: Page,
    *,
    attempt_number: int,
    staged_files: list[Path],
    prompt: str,
    output_path: Path,
    diagnostics_root: Path,
) -> tuple[AttemptRecord, Path]:
    attempt = AttemptRecord(attempt=attempt_number, staged_files=[str(path) for path in staged_files])
    attempt_dir = diagnostics_root / f"attempt-{attempt_number}"
    console_events: list[dict[str, str]] = []

    page.on(
        "console",
        lambda msg: console_events.append(
            {
                "type": msg.type,
                "text": msg.text,
            }
        ),
    )
    page.on(
        "pageerror",
        lambda err: console_events.append(
            {
                "type": "pageerror",
                "text": str(err),
            }
        ),
    )

    try:
        attempt.final_stage = "open_page"
        page.goto(CHATGPT_IMAGES_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        attempt.target_url = page.url
        ensure_logged_in(page, attempt)

        attempt.final_stage = "quality_mode"
        maybe_select_high_quality(page, attempt)

        attempt.final_stage = "upload_assets"
        upload_assets(page, attempt, staged_files)

        baseline_srcs = {str(item.get("src") or "") for item in generated_image_candidates(page)}

        attempt.final_stage = "fill_prompt"
        fill_prompt(page, attempt, prompt)

        attempt.final_stage = "send_prompt"
        send_prompt(page, attempt)

        attempt.final_stage = "wait_for_image"
        candidate = wait_for_generated_image(page, attempt, baseline_srcs)

        attempt.final_stage = "download_image"
        image_url = str(candidate.get("src") or "").strip()
        if not image_url:
            raise ChatGPTCoverError("download_image", "ChatGPT reported a generated image without a usable src URL")
        downloaded_path = download_generated_image(page, attempt, image_url, output_path)
        attempt.ok = True
        attempt.final_stage = "downloaded"
        return attempt, downloaded_path
    except ChatGPTCoverError as exc:
        attempt.ok = False
        attempt.final_stage = exc.stage
        attempt.failure_reason = str(exc)
        if exc.selector_path:
            attempt.selector_path.extend(exc.selector_path)
        capture_attempt_artifacts(attempt, page, attempt_dir, console_events)
        exc.attempt_record = attempt
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        attempt.ok = False
        attempt.final_stage = "playwright_error"
        attempt.failure_reason = str(exc)
        capture_attempt_artifacts(attempt, page, attempt_dir, console_events)
        wrapped = ChatGPTCoverError("playwright_error", str(exc), selector_path=attempt.selector_path)
        wrapped.attempt_record = attempt
        raise wrapped from exc
    except Exception as exc:
        attempt.ok = False
        attempt.final_stage = "unexpected_error"
        attempt.failure_reason = str(exc)
        capture_attempt_artifacts(attempt, page, attempt_dir, console_events)
        wrapped = ChatGPTCoverError("unexpected_error", str(exc), selector_path=attempt.selector_path)
        wrapped.attempt_record = attempt
        raise wrapped from exc
    finally:
        if not attempt.artifacts:
            attempt.artifacts = {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a ChatGPT Images cover using Playwright + a persistent Chrome profile.")
    parser.add_argument("--profile", default="openclaw")
    parser.add_argument("--user-data-dir", type=Path, help="Optional Chrome user-data directory override")
    parser.add_argument("--chrome-path", help="Optional Chrome executable path override")
    parser.add_argument("--cdp-endpoint", default=DEFAULT_OPENCLAW_CDP_ENDPOINT)
    parser.add_argument("--date", required=True, help="Date folder used for staging, e.g. 2026-04-07")
    parser.add_argument("--collage", required=True, type=Path, help="Local collage image path")
    parser.add_argument("--asset", action="append", default=[], type=Path, help="Additional reference asset path")
    parser.add_argument("--manifest", type=Path, help="Optional manifest.json; strongest assets are used when --asset is omitted")
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Download path inside /tmp/openclaw/downloads")
    parser.add_argument("--result-json", type=Path, help="Optional structured result JSON output path")
    parser.add_argument("--diag-dir", type=Path, help="Optional diagnostics directory override")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--close-tab", action="store_true", help="Kept for CLI compatibility; Playwright pages are always closed")
    parser.add_argument("--no-fallback", action="store_true", help="Do not fall back to the local collage after generic ChatGPT failures")
    args = parser.parse_args()

    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit("prompt file is empty")

    extra_assets = list(args.asset)
    if args.manifest and not extra_assets:
        if not args.manifest.exists():
            raise SystemExit(f"missing manifest: {args.manifest}")
        extra_assets = load_manifest_assets(args.manifest)

    all_paths = [args.collage, *extra_assets]
    validate_assets(all_paths)

    output_path = args.output or derive_output_path(args.date)
    if not str(output_path).startswith(str(DOWNLOADS_ROOT)):
        raise SystemExit(f"--output must stay within {DOWNLOADS_ROOT}")

    result_path = args.result_json or derive_result_path(output_path)
    diagnostics_root = args.diag_dir or derive_diagnostics_dir(output_path)
    diagnostics_root.mkdir(parents=True, exist_ok=True)

    stage_dir = UPLOADS_ROOT / args.date
    staged_files = stage_assets(stage_dir, all_paths)

    chrome_path = resolve_chrome_path(args.chrome_path)
    user_data_dir = resolve_user_data_dir(args.profile, args.user_data_dir)
    if not user_data_dir.exists():
        raise SystemExit(f"user-data directory does not exist: {user_data_dir}")

    attempts: list[AttemptRecord] = []
    login_failure: ChatGPTCoverError | None = None
    generic_failure: ChatGPTCoverError | None = None

    browser_mode = "persistent_context"
    with sync_playwright() as playwright:
        context, browser_mode, close_browser_context = launch_browser_context(
            playwright,
            user_data_dir=user_data_dir,
            chrome_path=chrome_path,
            cdp_endpoint=args.cdp_endpoint,
        )
        try:
            for attempt_number in range(1, max(1, args.max_attempts) + 1):
                page = context.new_page()
                try:
                    attempt, downloaded_path = run_attempt(
                        page,
                        attempt_number=attempt_number,
                        staged_files=staged_files,
                        prompt=prompt,
                        output_path=output_path,
                        diagnostics_root=diagnostics_root,
                    )
                    attempts.append(attempt)
                    result_payload = result_to_dict(
                        RunResult(
                            ok=True,
                            provider="chatgpt",
                            attempts=attempts,
                            final_stage="downloaded",
                            downloaded=str(downloaded_path),
                            artifacts={"result_json": str(result_path), "diagnostics_dir": str(diagnostics_root)},
                            prompt_file=str(args.prompt_file),
                            manifest=str(args.manifest) if args.manifest else None,
                            user_data_dir=str(user_data_dir),
                            browser_path=str(chrome_path),
                            browser_mode=browser_mode,
                        )
                    )
                    result_payload["image"] = str(downloaded_path)
                    write_json(result_path, result_payload)
                    print(json.dumps(result_payload, ensure_ascii=False, indent=2))
                    return 0
                except ChatGPTCoverError as exc:
                    failure_attempt = exc.attempt_record
                    if failure_attempt is None:
                        failure_attempt = AttemptRecord(
                            attempt=attempt_number,
                            ok=False,
                            final_stage=exc.stage,
                            target_url=page.url if page else None,
                            staged_files=[str(path) for path in staged_files],
                            selector_path=exc.selector_path,
                            failure_reason=str(exc),
                        )
                    attempts.append(failure_attempt)
                    if exc.login_required:
                        login_failure = exc
                        break
                    generic_failure = exc
                finally:
                    try:
                        page.close()
                    except PlaywrightError:
                        pass
        finally:
            close_browser_context()

    final_stage = "login_required" if login_failure else "chatgpt_failed"
    if login_failure or args.no_fallback:
        result_payload = result_to_dict(
            RunResult(
                ok=False,
                provider="chatgpt",
                attempts=attempts,
                final_stage=final_stage,
                downloaded=None,
                artifacts={"result_json": str(result_path), "diagnostics_dir": str(diagnostics_root)},
                fallback_reason=None,
                prompt_file=str(args.prompt_file),
                manifest=str(args.manifest) if args.manifest else None,
                user_data_dir=str(user_data_dir),
                browser_path=str(chrome_path),
                browser_mode=browser_mode,
            )
        )
        write_json(result_path, result_payload)
        print(json.dumps(result_payload, ensure_ascii=False, indent=2))
        return 1

    fallback_reason = (
        f"ChatGPT failed after {len(attempts)} attempt(s): {generic_failure}"
        if generic_failure
        else f"ChatGPT failed after {len(attempts)} attempt(s)"
    )
    result_payload = result_to_dict(
        RunResult(
            ok=True,
            provider="fallback_collage",
            attempts=attempts,
            final_stage="fallback_collage",
            downloaded=str(args.collage),
            artifacts={"result_json": str(result_path), "diagnostics_dir": str(diagnostics_root)},
            fallback_reason=fallback_reason,
            prompt_file=str(args.prompt_file),
            manifest=str(args.manifest) if args.manifest else None,
            user_data_dir=str(user_data_dir),
            browser_path=str(chrome_path),
            browser_mode=browser_mode,
        )
    )
    result_payload["image"] = str(args.collage)
    write_json(result_path, result_payload)
    print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
