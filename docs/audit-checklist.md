# Audit Checklist

Use this checklist for the next review pass.

## Cron And Runtime

- Confirm both automation files use `model = "gpt-5.5"` and `reasoning_effort = "high"`.
- Confirm both automation files set `cwds = ["/Users/dystopia/Desktop/AI-Daily-Reports"]`.
- Confirm prompts do not authorize silent fallback as success.
- Decide whether production jobs should eventually read from this repo-style folder instead of `/Users/dystopia/.openclaw/workspace`.

## Path Hygiene

- Search for `/Users/dystopia/`, `.openclaw`, and `.codex` references before turning the snapshot into a portable repo.
- Classify hard-coded paths into required user-local paths, production roots, and avoidable coupling.
- Replace avoidable path coupling with a single configurable workspace root before making this a runnable repo.

## Discovery And Source Quality

- Check `src/pipeline/tech_daily_prepare_discovery.py` for candidate-count thresholds.
- Check source de-duplication and merged-candidate precedence.
- Check X-reader usage limits and fallback behavior.
- Verify source-pack/reference-pack metadata preserves enough provenance for every selected item.

## Editorial Output

- Check `src/pipeline/ai_daily_llm_content.py` for model policy and mock/fallback switches.
- Check `src/intelligence/references/report-template.md`.
- Check `src/intelligence/references/title-cover-playbook.md` before changing title or cover behavior.
- Check `samples/2026-04-28/final/content-manifest.json` for title length, card copy, and item-level structure.

## Image And Cover

- Check `src/media/scripts/fetch_story_images.py`.
- Confirm `primary_hook`, `wechat_title`, `video_title`, and `bilibili_title` use the same unified public title.
- Confirm cover generation uses the imagegen skill handoff brief before deterministic Swift fallback.
- Confirm Lumi remains present and recognizable, but non-Lumi visual composition can change freely.
- Confirm every selected story requires at least one real source visual.
- Confirm site logos, placeholders, and generic fallback cards cannot pass as story visuals.
- Confirm cover copy flows through title pack and cover review.

## Video

- Confirm `src/video/scripts/build_tech_daily_video.py` requires Remotion output for production.
- Confirm `tts.effective_provider == "fish-speech"` is enforced.
- Confirm remote fallback, macOS `say`, silent audio, and offline slideshow are treated as failures.
- Confirm titled MP4 copies are derived from `publish/title-pack.json`.
- Review Remotion text-fit and layout components for long Chinese titles.

## Publishing

- Confirm Telegram and Bilibili upload manifests point to canonical `final/video.mp4`.
- Confirm WeChat DOCX starts with the daily cover image.
- Confirm publishing scripts read from manifests instead of regenerating divergent copy.

## Sample Evidence

- Keep generated run outputs outside the repository unless a deliberately minimized fixture is added.
