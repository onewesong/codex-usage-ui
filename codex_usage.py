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
from typing import Any, Dict, Optional, Tuple


def codex_home() -> Path:
    env_path = os.environ.get("CODEX_HOME")
    return Path(env_path) if env_path else Path.home() / ".codex"


def load_auth(home: Path) -> tuple[str, str]:
    auth_path = home / "auth.json"
    if not auth_path.exists():
        raise FileNotFoundError(
            f"{auth_path} does not exist; run `codex login chatgpt` before using this script."
        )
    data = json.loads(auth_path.read_text(encoding="utf-8"))
    tokens = data.get("tokens")
    if not tokens:
        raise ValueError("no ChatGPT tokens found in auth.json (run `codex login chatgpt`).")
    access_token = tokens.get("access_token")
    if not access_token:
        raise ValueError("missing `access_token` in auth.json")
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


def format_rate_limit_window(name: str, window: Dict[str, Any]) -> str:
    if not window:
        return f"{name}：无详细信息"
    used = window.get("used_percent")
    limit_seconds = window.get("limit_window_seconds")
    resets_at = window.get("reset_at")
    details = []
    if isinstance(used, (int, float)):
        details.append(f"已用 {used:.0f}%")
    if isinstance(limit_seconds, (int, float)):
        seconds = int(limit_seconds)
        minutes = seconds // 60
        if minutes:
            hours = seconds / 3600
            if hours.is_integer():
                hours_label = f"{int(hours)} 小时"
            else:
                hours_label = f"{hours:.1f} 小时"
            details.append(f"{minutes} 分钟窗口 ({hours_label})")
        else:
            details.append(f"{seconds} 秒窗口")
    if resets_at:
        resets = datetime.fromtimestamp(resets_at, tz=timezone.utc).astimezone()
        details.append(f"将在 {resets.strftime('%Y-%m-%d %H:%M:%S')} 重置")
    detail_str = "，".join(details) if details else "无详细信息"
    return f"{name}：{detail_str}"


def describe_rate_limit(label: str, payload: Dict[str, Any]) -> None:
    allowed = payload.get("allowed")
    limit_reached = payload.get("limit_reached")
    status_parts = []
    if allowed is not None:
        status_parts.append("✅ 已允许" if allowed else "❌ 未允许")
    if limit_reached is not None:
        status_parts.append("🚨 已达上限" if limit_reached else "⚡ 未达上限")
    status = "，".join(status_parts) if status_parts else "状态未知"
    print(f"{label}：{status}")
    primary = payload.get("primary_window")
    secondary = payload.get("secondary_window")
    if primary:
        print("  " + format_rate_limit_window("主窗口", primary))
    if secondary:
        print("  " + format_rate_limit_window("辅助窗口", secondary))


def human_summary(data: Dict[str, Any]) -> None:
    plan = data.get("plan_type") or "未知"
    print(f"📦 订阅计划：{plan}")
    rate_limit = data.get("rate_limit")
    if isinstance(rate_limit, dict):
        describe_rate_limit("⚡ 离线请求限额", rate_limit)
    code_review_limit = data.get("code_review_rate_limit")
    if isinstance(code_review_limit, dict):
        describe_rate_limit("🛠️ 代码评审限额", code_review_limit)
    credits = data.get("credits")
    if isinstance(credits, dict):
        has_credits = credits.get("has_credits")
        unlimited = credits.get("unlimited")
        balance = credits.get("balance")
        parts = []
        if has_credits is not None:
            parts.append("✅ 有额度" if has_credits else "❌ 无额度")
        if unlimited is not None:
            parts.append("♾️ 无限" if unlimited else "🔒 有上限")
        if balance:
            parts.append(f"余额 {balance}")
        status = "，".join(parts) if parts else "状态未知"
        print(f"💰 额度状态：{status}")


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
    return f"约{' '.join(parts)}后重置"


def format_reset_at(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)):
        return "未知"
    reset_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return reset_time.strftime("%Y-%m-%d %H:%M:%S")
