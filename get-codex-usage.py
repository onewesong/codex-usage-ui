#!/usr/bin/env python3
"""
Fetch the current Codex rate-limit/credit snapshot using the cached ChatGPT tokens.
"""

from __future__ import annotations

import argparse

from codex_usage import fetch_usage_snapshot, human_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Codex usage via cached auth.")
    parser.add_argument(
        "--human",
        action="store_true",
        help="format the result into a human readable summary rather than raw JSON",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="print only the raw JSON body without headers or extra summaries",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    usage_url, body, data = fetch_usage_snapshot()
    if args.json_only:
        print(body)
        return
    print(f"GET {usage_url}")
    if args.human:
        human_summary(data)
    else:
        print(body)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"error: {exc}") from exc
