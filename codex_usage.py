#!/usr/bin/env python3
"""
Shared helpers for fetching and formatting Codex usage data.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


def codex_home() -> Path:
    env_path = os.environ.get("CODEX_HOME")
    return Path(env_path) if env_path else Path.home() / ".codex"


def auth_path(home: Path) -> Path:
    override = os.environ.get("CODEX_AUTH_PATH")
    if override:
        return Path(override).expanduser()
    return home / "auth.json"


def load_auth(home: Path) -> tuple[str, str]:
    current_auth_path = auth_path(home)
    if not current_auth_path.exists():
        raise FileNotFoundError(
            f"{current_auth_path} does not exist; run `codex login chatgpt` "
            "or set `CODEX_AUTH_PATH` to a valid auth.json path."
        )
    data = json.loads(current_auth_path.read_text(encoding="utf-8"))
    tokens = data.get("tokens")
    if not tokens:
        raise ValueError(
            f"no ChatGPT tokens found in {current_auth_path} "
            "(run `codex login chatgpt` or check `CODEX_AUTH_PATH`)."
        )
    access_token = tokens.get("access_token")
    if not access_token:
        raise ValueError(f"missing `access_token` in {current_auth_path}")
    account_id = tokens.get("account_id") or ""
    return access_token, account_id


def parse_config_base_url(home: Path) -> Optional[str]:
    config_path = home / "config.toml"
    if not config_path.exists():
        return None
    try:
        import tomllib  # type: ignore[import]

        raw = tomllib.load(config_path.open("rb"))
        base_url = raw.get("chatgpt_base_url")
        if isinstance(base_url, str) and base_url.strip():
            return base_url.strip()
        return None
    except ModuleNotFoundError:
        pass
    except Exception:
        # Best-effort fallback to manual parsing instead of failing entirely.
        pass

    value = None
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, raw_value = [part.strip() for part in line.split("=", 1)]
        if key != "chatgpt_base_url":
            continue
        if (raw_value.startswith('"') and raw_value.endswith('"')) or (
            raw_value.startswith("'") and raw_value.endswith("'")
        ):
            raw_value = raw_value[1:-1]
        if raw_value:
            value = raw_value
            break
    return value


def build_usage_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/backend-api"):
        return f"{normalized}/wham/usage"
    return f"{normalized}/api/codex/usage"


def fetch_usage(usage_url: str, access_token: str, account_id: str) -> Tuple[str, Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id

    req = urllib.request.Request(usage_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return body, data
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        raise SystemExit(
            f"request to {usage_url} failed: {err.code} {err.reason}\n{detail}"
        ) from err


def fetch_usage_snapshot(home: Optional[Path] = None) -> Tuple[str, str, Dict[str, Any]]:
    active_home = home or codex_home()
    access_token, account_id = load_auth(active_home)
    configured_base_url = parse_config_base_url(active_home)
    base_url = configured_base_url or "https://chatgpt.com/backend-api"
    usage_url = build_usage_url(base_url)
    body, data = fetch_usage(usage_url, access_token, account_id)
    return usage_url, body, data


def format_status(payload: Dict[str, Any]) -> str:
    allowed = payload.get("allowed")
    limit_reached = payload.get("limit_reached")
    if allowed is False:
        return "不可用"
    if limit_reached:
        return "已达上限"
    if allowed:
        return "可用"
    return "未知"


def emit_kv_rows(rows: Iterable[Tuple[str, str]]) -> None:
    normalized = [(label, value) for label, value in rows if value]
    if not normalized:
        return
    width = max(len(label) for label, _ in normalized)
    for label, value in normalized:
        print(f"  {label:<{width}}  {value}")


def emit_window_block(title: str, window: Dict[str, Any]) -> None:
    if not isinstance(window, dict) or not window:
        return
    used_percent = int(window.get("used_percent", 0))
    print(f"- {title}（{format_window_span(window.get('limit_window_seconds'))}）")
    emit_kv_rows(
        [
            ("已使用", f"{used_percent}%"),
            ("进度条", progress_bar_text(used_percent)),
            ("重置剩余", format_remaining(window.get("reset_after_seconds"))),
            ("重置时间", format_reset_at(window.get("reset_at"))),
        ]
    )


def emit_section(title: str) -> None:
    print()
    print(f"[{title}]")


def human_summary(data: Dict[str, Any]) -> None:
    plan = data.get("plan_type") or "未知"
    print(f"订阅计划: {plan}")

    rate_limit = data.get("rate_limit")
    if isinstance(rate_limit, dict):
        emit_section("配额使用详情")
        emit_window_block("主窗口", rate_limit.get("primary_window"))
        emit_window_block("周窗口", rate_limit.get("secondary_window"))

    additional_limits = data.get("additional_rate_limits")
    if isinstance(additional_limits, list):
        for item in additional_limits:
            if not isinstance(item, dict):
                continue
            limit_name = item.get("limit_name") or "附加"
            limit = item.get("rate_limit") if isinstance(item.get("rate_limit"), dict) else {}
            primary = limit.get("primary_window") if isinstance(limit.get("primary_window"), dict) else {}
            secondary = (
                limit.get("secondary_window") if isinstance(limit.get("secondary_window"), dict) else {}
            )
            emit_section(f"{limit_name} 额外配额")
            emit_kv_rows(
                [
                    ("功能代号", str(item.get("metered_feature") or "-")),
                    ("状态", format_status(limit)),
                    (
                        f"主窗口已用（{format_window_span(primary.get('limit_window_seconds'))}）",
                        f"{int(primary.get('used_percent', 0))}%",
                    ),
                    (
                        "主窗口进度",
                        progress_bar_text(int(primary.get("used_percent", 0))),
                    ),
                    (
                        f"周窗口已用（{format_window_span(secondary.get('limit_window_seconds'))}）",
                        f"{int(secondary.get('used_percent', 0))}%",
                    ),
                    (
                        "周窗口进度",
                        progress_bar_text(int(secondary.get("used_percent", 0))),
                    ),
                ]
            )

    credits = data.get("credits")
    if isinstance(credits, dict):
        emit_section("积分余额")
        emit_kv_rows(
            [
                ("余额", str(credits.get("balance", "0"))),
                ("无限积分", "是" if credits.get("unlimited") else "否"),
                ("本地消息估算", pair_text(credits.get("approx_local_messages"))),
                ("云端消息估算", pair_text(credits.get("approx_cloud_messages"))),
            ]
        )


def format_window_span(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "未知"
    total = int(seconds)
    day = 24 * 3600
    hour = 3600
    minute = 60
    if total % day == 0:
        return f"{total // day}天"
    if total % hour == 0:
        return f"{total // hour}小时"
    if total >= hour:
        hours = total // hour
        minutes = (total % hour) // minute
        return f"{hours}小时{minutes}分钟" if minutes else f"{hours}小时"
    if total >= minute:
        return f"{total // minute}分钟"
    return f"{total}秒"


def format_remaining(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "重置时间未知"
    total = max(0, int(seconds))
    day = 24 * 3600
    hour = 3600
    minute = 60
    parts = []
    days = total // day
    hours = (total % day) // hour
    minutes = (total % hour) // minute
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes or not parts:
        parts.append(f"{minutes}分钟")
    return f"约{''.join(parts)}后重置"


def format_reset_at(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)):
        return "未知"
    reset_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return reset_time.strftime("%Y-%m-%d %H:%M:%S")


def pair_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]} / {value[1]}"
    return "未知"


def progress_bar_text(percent: int, width: int = 20) -> str:
    bounded = max(0, min(percent, 100))
    filled = round(bounded / 100 * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty} {bounded}%"
