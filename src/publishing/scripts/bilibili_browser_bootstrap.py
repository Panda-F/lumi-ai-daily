#!/usr/bin/env python3

from __future__ import annotations

import argparse

from browser_bootstrap_common import DEFAULT_PROFILE, bootstrap_platform, print_bootstrap_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open and inspect the Bilibili creator upload page in the OpenClaw browser.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="OpenClaw browser profile name")
    parser.add_argument("--url", default=None, help="Optional creator URL override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = bootstrap_platform("bilibili", profile=args.profile, url=args.url)
    if result["state"] == "ready_for_compose":
        result["state"] = "ready_for_upload"
        result["next_step"] = "The creator upload surface looks available."
    return print_bootstrap_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
