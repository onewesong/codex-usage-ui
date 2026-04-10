#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from typing import Any, Dict

from codex_usage import fetch_usage_snapshot
from history_store import mark_history_check_failed, save_history_snapshot_if_changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Codex usage history on an interval.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help="seconds between collection runs (default: 300)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="collect only once and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print each collection result as JSON",
    )
    parser.add_argument(
        "--source",
        default="collector",
        help="history source label written into status metadata (default: collector)",
    )
    return parser.parse_args()


def timestamp_text(unix_ts: int | None) -> str:
    if not unix_ts:
        return "unknown"
    return datetime.fromtimestamp(unix_ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def collect_once(source: str = "collector") -> Dict[str, Any]:
    try:
        _, _, data = fetch_usage_snapshot()
        result = save_history_snapshot_if_changed(data, source=source)
    except Exception as exc:
        result = mark_history_check_failed(str(exc), source=source)
    return result


def print_result(result: Dict[str, Any], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(result, ensure_ascii=False))
        return

    checked_at = timestamp_text(result.get("sampled_at"))
    status = result.get("result")
    if status == "saved":
        print(
            f"{checked_at} saved {result.get('inserted_series_count', 0)} points "
            f"(checked {result.get('checked_series_count', 0)} series)"
        )
    elif status == "unchanged":
        print(
            f"{checked_at} unchanged "
            f"(checked {result.get('checked_series_count', 0)} series)"
        )
    elif status == "no_data":
        print(f"{checked_at} no_data")
    else:
        print(f"{checked_at} error {result.get('error', 'unknown error')}")


def main() -> None:
    args = parse_args()
    interval_seconds = max(1, args.interval_seconds)

    while True:
        result = collect_once(args.source)
        print_result(result, args.json)
        if args.once:
            return
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
