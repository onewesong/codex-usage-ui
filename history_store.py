#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd


DEFAULT_HISTORY_DB = Path.home() / ".codex-usage-ui" / "history.sqlite3"
HISTORY_COLUMNS = [
    "id",
    "sampled_at",
    "account_id",
    "plan_type",
    "metric_group",
    "metric_name",
    "series_label",
    "limit_name",
    "metered_feature",
    "window_seconds",
    "used_percent",
    "reset_at",
    "allowed",
    "limit_reached",
]
RANGE_WINDOWS = {
    "24H": timedelta(hours=24),
    "7D": timedelta(days=7),
    "30D": timedelta(days=30),
    "全部": None,
}
HISTORY_STATUS_DEFAULTS = {
    "last_checked_at": None,
    "last_saved_at": None,
    "last_result": "尚未采样",
    "last_inserted_count": 0,
    "last_source": None,
    "last_error": None,
}
SERIES_ID_COLUMNS = (
    "metric_group",
    "metric_name",
    "series_label",
    "limit_name",
    "metered_feature",
)


def history_db_path() -> Path:
    override = os.environ.get("CODEX_USAGE_DB_PATH")
    if override:
        return Path(override).expanduser()
    return DEFAULT_HISTORY_DB


def ensure_history_db(db_path: Optional[Path] = None) -> Path:
    active_path = db_path or history_db_path()
    active_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(active_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sampled_at INTEGER NOT NULL,
                account_id TEXT,
                plan_type TEXT,
                metric_group TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                series_label TEXT NOT NULL,
                limit_name TEXT,
                metered_feature TEXT,
                window_seconds INTEGER,
                used_percent REAL,
                reset_at INTEGER,
                allowed INTEGER,
                limit_reached INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_samples_sampled_at ON usage_samples(sampled_at)"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_samples_metric
            ON usage_samples(metric_group, metric_name, limit_name, metered_feature, series_label)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history_status (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                last_checked_at INTEGER,
                last_saved_at INTEGER,
                last_result TEXT,
                last_inserted_count INTEGER NOT NULL DEFAULT 0,
                last_source TEXT,
                last_error TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO history_status (
                singleton,
                last_checked_at,
                last_saved_at,
                last_result,
                last_inserted_count,
                last_source,
                last_error
            ) VALUES (1, NULL, NULL, '尚未采样', 0, NULL, NULL)
            ON CONFLICT(singleton) DO NOTHING
            """
        )
    return active_path


def _bool_to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _window_record(
    *,
    sampled_at: int,
    account_id: str,
    plan_type: str,
    metric_group: str,
    metric_name: str,
    series_label: str,
    parent_limit: Dict[str, Any],
    window: Dict[str, Any],
    limit_name: Optional[str] = None,
    metered_feature: Optional[str] = None,
) -> Dict[str, Any]:
    used_percent = window.get("used_percent")
    window_seconds = window.get("limit_window_seconds")
    reset_at = window.get("reset_at")
    return {
        "sampled_at": sampled_at,
        "account_id": account_id,
        "plan_type": plan_type,
        "metric_group": metric_group,
        "metric_name": metric_name,
        "series_label": series_label,
        "limit_name": limit_name,
        "metered_feature": metered_feature,
        "window_seconds": int(window_seconds) if isinstance(window_seconds, (int, float)) else None,
        "used_percent": float(used_percent) if isinstance(used_percent, (int, float)) else None,
        "reset_at": int(reset_at) if isinstance(reset_at, (int, float)) else None,
        "allowed": _bool_to_int(parent_limit.get("allowed")),
        "limit_reached": _bool_to_int(parent_limit.get("limit_reached")),
    }


def extract_history_samples(data: Dict[str, Any], sampled_at: Optional[int] = None) -> List[Dict[str, Any]]:
    timestamp = sampled_at or int(datetime.now(timezone.utc).timestamp())
    account_id = str(data.get("account_id") or "")
    plan_type = str(data.get("plan_type") or "")
    rows: List[Dict[str, Any]] = []

    rate_limit = data.get("rate_limit")
    if isinstance(rate_limit, dict):
        primary = rate_limit.get("primary_window")
        secondary = rate_limit.get("secondary_window")
        if isinstance(primary, dict):
            rows.append(
                _window_record(
                    sampled_at=timestamp,
                    account_id=account_id,
                    plan_type=plan_type,
                    metric_group="rate_limit",
                    metric_name="main_usage",
                    series_label="主窗口",
                    parent_limit=rate_limit,
                    window=primary,
                )
            )
        if isinstance(secondary, dict):
            rows.append(
                _window_record(
                    sampled_at=timestamp,
                    account_id=account_id,
                    plan_type=plan_type,
                    metric_group="rate_limit",
                    metric_name="weekly_usage",
                    series_label="周窗口",
                    parent_limit=rate_limit,
                    window=secondary,
                )
            )

    additional_limits = data.get("additional_rate_limits")
    if isinstance(additional_limits, list):
        for item in additional_limits:
            if not isinstance(item, dict):
                continue
            limit = item.get("rate_limit")
            if not isinstance(limit, dict):
                continue
            limit_name = str(item.get("limit_name") or "附加")
            metered_feature = str(item.get("metered_feature") or "")
            primary = limit.get("primary_window")
            secondary = limit.get("secondary_window")
            if isinstance(primary, dict):
                rows.append(
                    _window_record(
                        sampled_at=timestamp,
                        account_id=account_id,
                        plan_type=plan_type,
                        metric_group="additional_rate_limit",
                        metric_name="main_usage",
                        series_label="主窗口",
                        parent_limit=limit,
                        window=primary,
                        limit_name=limit_name,
                        metered_feature=metered_feature,
                    )
                )
            if isinstance(secondary, dict):
                rows.append(
                    _window_record(
                        sampled_at=timestamp,
                        account_id=account_id,
                        plan_type=plan_type,
                        metric_group="additional_rate_limit",
                        metric_name="weekly_usage",
                        series_label="周窗口",
                        parent_limit=limit,
                        window=secondary,
                        limit_name=limit_name,
                        metered_feature=metered_feature,
                    )
                )
    return rows


def _series_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record.get(column) for column in SERIES_ID_COLUMNS)


def _load_latest_rows(conn: sqlite3.Connection, rows: Sequence[Dict[str, Any]]) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    latest_by_key: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        metric_group, metric_name, series_label, limit_name, metered_feature = _series_key(row)
        current = conn.execute(
            """
            SELECT
                metric_group,
                metric_name,
                series_label,
                limit_name,
                metered_feature,
                used_percent,
                allowed,
                limit_reached,
                reset_at
            FROM usage_samples
            WHERE metric_group = ?
              AND metric_name = ?
              AND series_label = ?
              AND COALESCE(limit_name, '') = COALESCE(?, '')
              AND COALESCE(metered_feature, '') = COALESCE(?, '')
            ORDER BY sampled_at DESC, id DESC
            LIMIT 1
            """,
            (metric_group, metric_name, series_label, limit_name, metered_feature),
        ).fetchone()
        if current is None:
            continue
        latest_by_key[_series_key(row)] = {
            "used_percent": current[5],
            "allowed": current[6],
            "limit_reached": current[7],
            "reset_at": current[8],
        }
    return latest_by_key


def _is_zero_usage(value: Any) -> bool:
    return value in (0, 0.0, None)


def _has_material_change(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> bool:
    if previous is None:
        return True

    for column in ("used_percent", "allowed", "limit_reached"):
        if current.get(column) != previous.get(column):
            return True

    current_used = current.get("used_percent")
    previous_used = previous.get("used_percent")
    if _is_zero_usage(current_used) and _is_zero_usage(previous_used):
        # Some rolling windows report reset_at as "now + window" when usage is zero.
        # That value drifts forward on every poll and would otherwise create noisy duplicates.
        return False

    return current.get("reset_at") != previous.get("reset_at")


def _upsert_history_status(
    conn: sqlite3.Connection,
    *,
    checked_at: int,
    saved_at: Optional[int],
    result: str,
    inserted_count: int,
    source: Optional[str],
    error: Optional[str],
) -> None:
    conn.execute(
        """
        UPDATE history_status
        SET
            last_checked_at = ?,
            last_saved_at = COALESCE(?, last_saved_at),
            last_result = ?,
            last_inserted_count = ?,
            last_source = ?,
            last_error = ?
        WHERE singleton = 1
        """,
        (checked_at, saved_at, result, inserted_count, source, error),
    )


def save_history_snapshot_if_changed(
    data: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
    sampled_at: Optional[int] = None,
    source: str = "ui",
) -> Dict[str, Any]:
    rows = extract_history_samples(data, sampled_at=sampled_at)
    checked_at = sampled_at or int(datetime.now(timezone.utc).timestamp())
    active_path = ensure_history_db(db_path)
    if not rows:
        with sqlite3.connect(active_path) as conn:
            _upsert_history_status(
                conn,
                checked_at=checked_at,
                saved_at=None,
                result="no_data",
                inserted_count=0,
                source=source,
                error=None,
            )
        return {
            "checked_series_count": 0,
            "inserted_series_count": 0,
            "sampled_at": checked_at,
            "result": "no_data",
            "saved": False,
            "db_path": str(active_path),
        }

    with sqlite3.connect(active_path) as conn:
        latest_by_key = _load_latest_rows(conn, rows)
        changed_rows = [
            row for row in rows if _has_material_change(row, latest_by_key.get(_series_key(row)))
        ]
        if changed_rows:
            conn.executemany(
                """
                INSERT INTO usage_samples (
                    sampled_at,
                    account_id,
                    plan_type,
                    metric_group,
                    metric_name,
                    series_label,
                    limit_name,
                    metered_feature,
                    window_seconds,
                    used_percent,
                    reset_at,
                    allowed,
                    limit_reached
                ) VALUES (
                    :sampled_at,
                    :account_id,
                    :plan_type,
                    :metric_group,
                    :metric_name,
                    :series_label,
                    :limit_name,
                    :metered_feature,
                    :window_seconds,
                    :used_percent,
                    :reset_at,
                    :allowed,
                    :limit_reached
                )
                """,
                changed_rows,
            )
            result = "saved"
            saved_at = checked_at
        else:
            result = "unchanged"
            saved_at = None

        _upsert_history_status(
            conn,
            checked_at=checked_at,
            saved_at=saved_at,
            result=result,
            inserted_count=len(changed_rows),
            source=source,
            error=None,
        )

    return {
        "checked_series_count": len(rows),
        "inserted_series_count": len(changed_rows),
        "sampled_at": checked_at,
        "result": result,
        "saved": bool(changed_rows),
        "db_path": str(active_path),
    }


def mark_history_check_failed(
    error: str,
    *,
    db_path: Optional[Path] = None,
    checked_at: Optional[int] = None,
    source: str = "collector",
) -> Dict[str, Any]:
    active_path = ensure_history_db(db_path)
    timestamp = checked_at or int(datetime.now(timezone.utc).timestamp())
    with sqlite3.connect(active_path) as conn:
        _upsert_history_status(
            conn,
            checked_at=timestamp,
            saved_at=None,
            result="error",
            inserted_count=0,
            source=source,
            error=error,
        )
    return {
        "checked_series_count": 0,
        "inserted_series_count": 0,
        "sampled_at": timestamp,
        "result": "error",
        "saved": False,
        "error": error,
        "db_path": str(active_path),
    }


def load_history_status(db_path: Optional[Path] = None) -> Dict[str, Any]:
    active_path = ensure_history_db(db_path)
    with sqlite3.connect(active_path) as conn:
        row = conn.execute(
            """
            SELECT
                last_checked_at,
                last_saved_at,
                last_result,
                last_inserted_count,
                last_source,
                last_error
            FROM history_status
            WHERE singleton = 1
            """
        ).fetchone()

    if row is None:
        return dict(HISTORY_STATUS_DEFAULTS)

    return {
        "last_checked_at": row[0],
        "last_saved_at": row[1],
        "last_result": row[2] or HISTORY_STATUS_DEFAULTS["last_result"],
        "last_inserted_count": row[3] or 0,
        "last_source": row[4],
        "last_error": row[5],
    }


def load_history_samples(range_key: str = "7D", db_path: Optional[Path] = None) -> pd.DataFrame:
    active_path = ensure_history_db(db_path)
    if range_key not in RANGE_WINDOWS:
        raise ValueError(f"unsupported range key: {range_key}")

    params: List[Any] = []
    query = "SELECT * FROM usage_samples"
    window = RANGE_WINDOWS[range_key]
    if window is not None:
        cutoff = int((datetime.now(timezone.utc) - window).timestamp())
        query += " WHERE sampled_at >= ?"
        params.append(cutoff)
    query += " ORDER BY sampled_at ASC, id ASC"

    with sqlite3.connect(active_path) as conn:
        frame = pd.read_sql_query(query, conn, params=params)

    if frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    local_tz = datetime.now().astimezone().tzinfo
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"], unit="s", utc=True)
    if local_tz is not None:
        frame["sampled_at"] = frame["sampled_at"].dt.tz_convert(local_tz)
    frame["sampled_at"] = frame["sampled_at"].dt.tz_localize(None)
    return frame
