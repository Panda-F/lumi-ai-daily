#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ModuleNotFoundError:
    print(
        "Missing dependency: playwright. Install it with `python3 -m pip install --user playwright`.",
        file=sys.stderr,
    )
    raise SystemExit(2)

os.environ.setdefault("NODE_NO_WARNINGS", "1")


UPLOADS_ROOT = Path("/tmp/openclaw/uploads")
DOWNLOADS_ROOT = Path("/tmp/openclaw/downloads")
GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_OPENCLAW_USER_DATA = Path("/Users/dystopia/.openclaw/browser/openclaw/user-data")
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_OPENCLAW_CDP_ENDPOINT = "http://127.0.0.1:18800"


class GeminiCoverError(RuntimeError):
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


@dataclass
class AttemptRecord:
    attempt: int
    ok: bool = False
    final_stage: str = "pending"
    target_url: str | None = None
    staged_files: list[str] = field(default_factory=list)
    selector_path: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    ok: bool
    provider: str
    attempts: list[AttemptRecord]
    final_stage: str
    downloaded: str | None
    artifacts: dict[str, str]
    fallback_reason: str | None = None
    prompt_file: str | None = None
    manifest: str | None = None
    user_data_dir: str | None = None
    browser_path: str | None = None
    browser_mode: str | None = None


def regex_for_names(names: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(name) for name in names if name]
    return re.compile("|".join(escaped), re.IGNORECASE)


def derive_output_path(date_value: str) -> Path:
    safe_date = re.sub(r"[^0-9-]+", "-", date_value).strip("-") or "latest"
    return DOWNLOADS_ROOT / f"gemini-cover-{safe_date}.png"


def derive_result_path(output_path: Path) -> Path:
    return output_path.with_suffix(".result.json")


def derive_diagnostics_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}.diagnostics"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest_assets(manifest_path: Path, *, limit: int = 4) -> list[Path]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths: list[Path] = []
    seen: set[str] = set()
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict):
            continue
        raw_file = asset.get("file")
        if not raw_file:
            continue
        path = Path(str(raw_file))
        if not path.exists():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
        if len(paths) >= limit:
            break
    return paths


def stage_assets(stage_dir: Path, paths: list[Path]) -> list[Path]:
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for path in paths:
        target = stage_dir / path.name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            index = 1
            while True:
                candidate = stage_dir / f"{stem}-{index}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                index += 1
        shutil.copy2(path, target)
        staged.append(target)
    return staged


def validate_assets(paths: list[Path]) -> None:
    if not paths:
        raise SystemExit("at least one collage asset is required")
    if len(paths) > 5:
        raise SystemExit("too many assets: keep the collage plus at most 4 reference images")
    for path in paths:
        if not path.exists():
            raise SystemExit(f"missing asset: {path}")
        if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise SystemExit(
                f"unsupported asset type for {path.name}; expected one of {sorted(SUPPORTED_IMAGE_SUFFIXES)}"
            )


def resolve_user_data_dir(profile: str, user_data_dir: Path | None) -> Path:
    if user_data_dir is not None:
        return user_data_dir.expanduser().resolve()
    if profile == "openclaw":
        return DEFAULT_OPENCLAW_USER_DATA
    return Path(f"/Users/dystopia/.openclaw/browser/{profile}/user-data").resolve()


def resolve_chrome_path(explicit: str | None) -> Path:
    candidates = [
        explicit,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path
    raise SystemExit("could not locate Google Chrome; pass --chrome-path explicitly")


def launch_browser_context(playwright, *, user_data_dir: Path, chrome_path: Path, cdp_endpoint: str):
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=str(chrome_path),
            headless=False,
            accept_downloads=True,
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        return context, "persistent_context", context.close
    except PlaywrightError as exc:
        message = str(exc)
        if "ProcessSingleton" not in message and "SingletonLock" not in message:
            raise
        browser = playwright.chromium.connect_over_cdp(cdp_endpoint, timeout=10000)
        if not browser.contexts:
            raise GeminiCoverError("browser_attach", f"connected over CDP but found no browser contexts at {cdp_endpoint}")
        context = browser.contexts[0]
        return context, "cdp_attach", lambda: None


def short_visible_text(text: str, *, limit: int = 4000) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def safe_locator_count(locator) -> int:
    try:
        return locator.count()
    except PlaywrightError:
        return 0


def safe_visible_text(page: Page) -> str:
    try:
        return short_visible_text(page.locator("body").inner_text(timeout=5000))
    except PlaywrightError:
        return ""


def first_working_action(
    attempt: AttemptRecord,
    candidates: list[tuple[str, Callable[[], Any]]],
    *,
    stage: str,
    error_message: str,
) -> tuple[str, Any]:
    last_error: Exception | None = None
    for label, action in candidates:
        attempt.selector_path.append(label)
        try:
            return label, action()
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_error = exc
            continue
    detail = f"{error_message}"
    if last_error is not None:
        detail = f"{detail}: {last_error}"
    raise GeminiCoverError(stage, detail, selector_path=attempt.selector_path[-len(candidates) :])


def require_visible(locator, *, timeout: int = 5000):
    locator.wait_for(state="visible", timeout=timeout)
    return locator


def wait_until(predicate: Callable[[], bool], *, timeout_s: float, interval_s: float = 1.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def capture_attempt_artifacts(
    attempt: AttemptRecord,
    page: Page | None,
    attempt_dir: Path,
    console_events: list[dict[str, str]],
) -> None:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    if page is not None:
        screenshot_path = attempt_dir / "page.png"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            attempt.artifacts["screenshot"] = str(screenshot_path)
        except PlaywrightError:
            pass

        html_path = attempt_dir / "page.html"
        try:
            html_path.write_text(page.content(), encoding="utf-8")
            attempt.artifacts["html"] = str(html_path)
        except PlaywrightError:
            pass

        visible_text = safe_visible_text(page)
        if visible_text:
            text_path = attempt_dir / "visible-text.txt"
            text_path.write_text(visible_text, encoding="utf-8")
            attempt.artifacts["visible_text"] = str(text_path)

        url_path = attempt_dir / "url.txt"
        try:
            url_path.write_text(page.url, encoding="utf-8")
            attempt.artifacts["url"] = str(url_path)
        except PlaywrightError:
            pass

    console_path = attempt_dir / "console.json"
    console_path.write_text(json.dumps(console_events, ensure_ascii=False, indent=2), encoding="utf-8")
    attempt.artifacts["console"] = str(console_path)


def ensure_logged_in(page: Page, attempt: AttemptRecord) -> None:
    if re.search(r"accounts\.google\.com", page.url, re.IGNORECASE):
        raise GeminiCoverError("login_required", "Gemini redirected to Google account login", login_required=True)

    login_markers = [
        r"登录",
        r"Sign in",
        r"Choose an account",
        r"Use your Google Account",
        r"Continue to Gemini",
    ]
    for marker in login_markers:
        locator = page.get_by_text(re.compile(marker, re.IGNORECASE))
        try:
            if locator.first.is_visible(timeout=1200):
                raise GeminiCoverError(
                    "login_required",
                    f"Gemini appears to require login: {marker}",
                    login_required=True,
                    selector_path=attempt.selector_path,
                )
        except PlaywrightTimeoutError:
            continue
        except PlaywrightError:
            continue


def normalize_to_new_chat(page: Page, attempt: AttemptRecord) -> None:
    candidates = [
        (
            "button:发起新对话|New chat",
            lambda: page.get_by_role("button", name=regex_for_names(["发起新对话", "New chat"])).first.click(timeout=3000),
        ),
        (
            "link:发起新对话|New chat",
            lambda: page.get_by_role("link", name=regex_for_names(["发起新对话", "New chat"])).first.click(timeout=3000),
        ),
    ]
    try:
        first_working_action(
            attempt,
            candidates,
            stage="new_chat",
            error_message="could not open a fresh Gemini chat",
        )
        page.wait_for_timeout(1200)
    except GeminiCoverError:
        # Gemini sometimes lands directly in a fresh compose surface. Only hard-fail if no composer appears later.
        return


def ensure_image_mode(page: Page, attempt: AttemptRecord) -> None:
    active_candidates = [
        (
            "button:取消选择制作图片|Deselect Create images",
            lambda: page.get_by_role(
                "button",
                name=regex_for_names(["取消选择“制作图片”", 'Deselect "Create images"', "取消选择"]),
            ).first.is_visible(timeout=1500),
        )
    ]
    for _label, action in active_candidates:
        attempt.selector_path.append(_label)
        try:
            if action():
                return
        except PlaywrightError:
            pass

    click_candidates = [
        (
            "button:制作图片|Create images|Generate images",
            lambda: page.get_by_role(
                "button",
                name=regex_for_names(["制作图片", "Create images", "Generate images"]),
            ).first.click(timeout=5000),
        ),
        (
            "text:制作图片|Create images|Generate images",
            lambda: page.get_by_text(
                regex_for_names(["制作图片", "Create images", "Generate images"])
            ).first.click(timeout=5000),
        ),
    ]
    first_working_action(
        attempt,
        click_candidates,
        stage="image_mode",
        error_message="could not switch Gemini into image mode",
    )
    page.wait_for_timeout(1500)


def upload_count(page: Page, staged_files: list[Path]) -> int:
    marker_counts = [
        safe_locator_count(page.get_by_role("button", name=regex_for_names(["移除文件", "Remove file", "Remove"]))),
        safe_locator_count(page.locator("[aria-label*='移除文件'], [aria-label*='Remove file'], [aria-label*='Remove']")),
    ]
    filename_hits = 0
    for path in staged_files:
        try:
            if page.get_by_text(path.name, exact=False).first.count() > 0:
                filename_hits += 1
        except PlaywrightError:
            continue
    marker_counts.append(filename_hits)
    return max(marker_counts)


def upload_assets(page: Page, attempt: AttemptRecord, staged_files: list[Path]) -> None:
    str_paths = [str(path) for path in staged_files]

    def try_dom_file_input() -> bool:
        inputs = page.locator("input[type='file']")
        count = safe_locator_count(inputs)
        for idx in range(count):
            attempt.selector_path.append(f"input[type=file]:{idx}")
            try:
                inputs.nth(idx).set_input_files(str_paths, timeout=3000)
                return True
            except PlaywrightError:
                continue
        return False

    if try_dom_file_input():
        pass
    else:
        menu_candidates = [
            (
                "button:打开文件上传菜单|Open file upload menu|Add files",
                lambda: page.get_by_role(
                    "button",
                    name=regex_for_names(["打开文件上传菜单", "Open file upload menu", "Add files"]),
                ).first.click(timeout=5000),
            ),
            (
                "button:添加文件|Upload file",
                lambda: page.get_by_role(
                    "button",
                    name=regex_for_names(["添加文件", "Upload file"]),
                ).first.click(timeout=5000),
            ),
        ]
        try:
            first_working_action(
                attempt,
                menu_candidates,
                stage="upload_menu",
                error_message="could not open the Gemini upload menu",
            )
            page.wait_for_timeout(600)
        except GeminiCoverError:
            pass

        if try_dom_file_input():
            pass
        else:
            chooser_candidates = [
                (
                    "menuitem:上传文件|Upload file",
                    lambda: require_visible(
                        page.get_by_role(
                            "menuitem",
                            name=regex_for_names(["上传文件", "Upload file"]),
                        ).first
                    ),
                ),
                (
                    "text:上传文件|Upload file",
                    lambda: require_visible(page.get_by_text(regex_for_names(["上传文件", "Upload file"])).first),
                ),
            ]
            label, locator = first_working_action(
                attempt,
                chooser_candidates,
                stage="upload_picker",
                error_message="could not find the Gemini upload file action",
            )
            with page.expect_file_chooser(timeout=8000) as chooser_info:
                locator.click(timeout=5000)
            attempt.selector_path.append(f"file_chooser:{label}")
            chooser_info.value.set_files(str_paths)

    if not wait_until(lambda: upload_count(page, staged_files) >= len(staged_files), timeout_s=25, interval_s=1.0):
        raise GeminiCoverError("upload_wait", "Gemini did not show uploaded asset previews in time", selector_path=attempt.selector_path)


def fill_prompt(page: Page, attempt: AttemptRecord, prompt: str) -> None:
    textbox_candidates = [
        (
            "textbox:为 Gemini 输入提示|Enter a prompt|Prompt",
            lambda: require_visible(
                page.get_by_role(
                    "textbox",
                    name=regex_for_names(["为 Gemini 输入提示", "Enter a prompt", "Prompt"]),
                ).first
            ),
        ),
        (
            "contenteditable:true",
            lambda: require_visible(page.locator("[contenteditable='true']").last),
        ),
        (
            "textarea",
            lambda: require_visible(page.locator("textarea").last),
        ),
    ]
    _label, textbox = first_working_action(
        attempt,
        textbox_candidates,
        stage="prompt_box",
        error_message="could not find the Gemini prompt composer",
    )
    textbox.click(timeout=5000)
    try:
        textbox.fill("", timeout=2000)
    except PlaywrightError:
        pass
    page.keyboard.insert_text(prompt)


def send_prompt(page: Page, attempt: AttemptRecord) -> None:
    send_candidates = [
        (
            "button:发送|Send",
            lambda: page.get_by_role("button", name=regex_for_names(["发送", "Send"])).first.click(timeout=5000),
        ),
        (
            "button:运行|Run",
            lambda: page.get_by_role("button", name=regex_for_names(["运行", "Run"])).first.click(timeout=5000),
        ),
    ]
    first_working_action(
        attempt,
        send_candidates,
        stage="send_prompt",
        error_message="could not submit the Gemini prompt",
    )


def wait_for_download(page: Page, attempt: AttemptRecord, output_path: Path) -> Path:
    download_button = page.get_by_role(
        "button",
        name=regex_for_names(["下载完整尺寸的图片", "Download full size image"]),
    ).first

    if not wait_until(lambda: download_button.is_visible(timeout=1000), timeout_s=240, interval_s=3.0):
        raise GeminiCoverError("wait_for_download", "Gemini did not expose a downloadable image in time", selector_path=attempt.selector_path)

    attempt.selector_path.append("button:下载完整尺寸的图片|Download full size image")
    with page.expect_download(timeout=60000) as download_info:
        download_button.click(timeout=5000)
    download = download_info.value
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(output_path))
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise GeminiCoverError("save_download", f"downloaded file missing or empty: {output_path}", selector_path=attempt.selector_path)
    if output_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise GeminiCoverError("save_download", f"unexpected downloaded suffix: {output_path.suffix}", selector_path=attempt.selector_path)
    return output_path


def run_attempt(
    page: Page,
    *,
    attempt_number: int,
    staged_files: list[Path],
    prompt: str,
    output_path: Path,
    diagnostics_root: Path,
) -> AttemptRecord:
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
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        attempt.target_url = page.url
        ensure_logged_in(page, attempt)

        attempt.final_stage = "new_chat"
        normalize_to_new_chat(page, attempt)
        ensure_logged_in(page, attempt)

        attempt.final_stage = "image_mode"
        ensure_image_mode(page, attempt)

        attempt.final_stage = "upload_assets"
        upload_assets(page, attempt, staged_files)

        attempt.final_stage = "fill_prompt"
        fill_prompt(page, attempt, prompt)

        attempt.final_stage = "send_prompt"
        send_prompt(page, attempt)

        attempt.final_stage = "download_image"
        wait_for_download(page, attempt, output_path)
        attempt.ok = True
        attempt.final_stage = "downloaded"
        return attempt
    except GeminiCoverError as exc:
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
        wrapped = GeminiCoverError("playwright_error", str(exc), selector_path=attempt.selector_path)
        wrapped.attempt_record = attempt
        raise wrapped from exc
    except Exception as exc:
        attempt.ok = False
        attempt.final_stage = "unexpected_error"
        attempt.failure_reason = str(exc)
        capture_attempt_artifacts(attempt, page, attempt_dir, console_events)
        wrapped = GeminiCoverError("unexpected_error", str(exc), selector_path=attempt.selector_path)
        wrapped.attempt_record = attempt
        raise wrapped from exc
    finally:
        if not attempt.artifacts:
            attempt.artifacts = {}


def result_to_dict(result: RunResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["attempts"] = [asdict(attempt) for attempt in result.attempts]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Gemini cover image using Playwright + a persistent Chrome profile.")
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
    parser.add_argument("--no-fallback", action="store_true", help="Do not fall back to the local collage after generic Gemini failures")
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
    login_failure: GeminiCoverError | None = None
    generic_failure: GeminiCoverError | None = None

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
                    attempt = run_attempt(
                        page,
                        attempt_number=attempt_number,
                        staged_files=staged_files,
                        prompt=prompt,
                        output_path=output_path,
                        diagnostics_root=diagnostics_root,
                    )
                    attempts.append(attempt)
                    result = RunResult(
                        ok=True,
                        provider="gemini",
                        attempts=attempts,
                        final_stage="downloaded",
                        downloaded=str(output_path),
                        artifacts={"result_json": str(result_path), "diagnostics_dir": str(diagnostics_root)},
                        prompt_file=str(args.prompt_file),
                        manifest=str(args.manifest) if args.manifest else None,
                        user_data_dir=str(user_data_dir),
                        browser_path=str(chrome_path),
                        browser_mode=browser_mode,
                    )
                    payload = result_to_dict(result)
                    write_json(result_path, payload)
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    return 0
                except GeminiCoverError as exc:
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

    final_stage = "login_required" if login_failure else "gemini_failed"
    if login_failure or args.no_fallback:
        result = RunResult(
            ok=False,
            provider="gemini",
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
        payload = result_to_dict(result)
        write_json(result_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    fallback_reason = (
        f"Gemini failed after {len(attempts)} attempt(s): {generic_failure}"
        if generic_failure
        else f"Gemini failed after {len(attempts)} attempt(s)"
    )
    result = RunResult(
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
    payload = result_to_dict(result)
    write_json(result_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
