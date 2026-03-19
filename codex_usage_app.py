#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from html import escape
from textwrap import dedent
from typing import Any, Dict, Iterable, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from codex_usage import (
    fetch_usage_snapshot,
    format_remaining,
    format_reset_at,
    format_window_span,
)
from history_store import (
    history_db_path,
    load_history_samples,
    load_history_status,
    save_history_snapshot_if_changed,
)


st.set_page_config(page_title="Codex 配额看板", layout="wide")
HISTORY_RANGE_OPTIONS = ["24H", "7D", "30D", "全部"]


def html_block(content: str) -> str:
    return dedent(content).strip()


def inject_css() -> None:
    st.markdown(
        """
        <style>
          :root {
            --bg: #252421;
            --panel: #32312d;
            --panel-border: rgba(255, 255, 255, 0.12);
            --text: #f5f4ef;
            --muted: #b9b6ad;
            --track: rgba(0, 0, 0, 0.22);
            --blue: #79a8df;
            --amber: #f5a623;
            --green: #7cc045;
            --red: #e56b6f;
          }

          .stApp {
            background:
              radial-gradient(circle at top left, rgba(255, 255, 255, 0.05), transparent 24%),
              linear-gradient(180deg, #282723 0%, var(--bg) 100%);
            color: var(--text);
          }

          .block-container {
            max-width: 1500px;
            padding-top: 2.2rem;
            padding-bottom: 3rem;
          }

          header[data-testid="stHeader"] {
            background: transparent;
          }

          [data-testid="stToolbar"] {
            visibility: hidden;
            height: 0;
            position: fixed;
          }

          .topbar {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-end;
            margin-bottom: 1.4rem;
          }

          .eyebrow {
            color: var(--muted);
            font-size: 0.95rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
          }

          .page-title {
            margin: 0.25rem 0 0;
            font-size: 2rem;
            line-height: 1.1;
            font-weight: 700;
          }

          .toolbar-meta {
            text-align: right;
            color: var(--muted);
            font-size: 0.96rem;
          }

          .toolbar-links {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 0.7rem;
            margin-bottom: 0.65rem;
          }

          .pill {
            display: inline-block;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 999px;
            padding: 0.32rem 0.75rem;
            margin-left: 0.45rem;
            color: var(--text);
            background: rgba(255, 255, 255, 0.03);
          }

          .github-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 42px;
            height: 42px;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(255, 255, 255, 0.03);
            color: var(--text);
            text-decoration: none;
            transition: transform 120ms ease, background 120ms ease, border-color 120ms ease;
          }

          .github-link:hover {
            transform: translateY(-1px);
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.22);
          }

          .github-link svg {
            width: 20px;
            height: 20px;
            fill: currentColor;
          }

          .refresh-meta {
            margin-top: 0.55rem;
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 0.45rem;
          }

          .refresh-text {
            color: var(--muted);
          }

          .stButton > button[kind="tertiary"] {
            min-width: 2rem;
            width: 2rem;
            height: 2rem;
            padding: 0;
            border-radius: 999px;
            border: 1px solid transparent !important;
            background: transparent !important;
            box-shadow: none !important;
            color: var(--muted) !important;
          }

          .stButton > button[kind="tertiary"]:hover {
            border-color: rgba(255, 255, 255, 0.16) !important;
            background: rgba(255, 255, 255, 0.04) !important;
            color: var(--text) !important;
          }

          .stButton > button[kind="tertiary"]:focus,
          .stButton > button[kind="tertiary"]:active {
            background: rgba(255, 255, 255, 0.06) !important;
            box-shadow: none !important;
          }

          .card {
            background: rgba(50, 49, 45, 0.96);
            border: 1px solid var(--panel-border);
            border-radius: 22px;
            padding: 1.6rem 2rem;
            margin-bottom: 1.3rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
          }

          .card-title {
            margin: 0 0 1.35rem;
            font-size: 1.2rem;
            font-weight: 700;
          }

          .window-block + .window-block {
            margin-top: 1.65rem;
          }

          .window-title {
            font-size: 1.05rem;
            color: var(--muted);
            font-weight: 700;
            margin-bottom: 0.85rem;
          }

          .window-meta {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: baseline;
            margin-bottom: 0.75rem;
          }

          .window-used {
            font-size: 1.1rem;
            font-weight: 700;
          }

          .window-reset {
            font-size: 0.98rem;
            color: #a5a29a;
            text-align: right;
          }

          .window-foot {
            margin-top: 0.5rem;
            color: #97948c;
            font-size: 0.86rem;
          }

          .metric-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
            padding: 0.6rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          }

          .metric-row:last-of-type {
            border-bottom: 0;
          }

          .metric-label {
            color: var(--muted);
            font-size: 0.98rem;
            font-weight: 600;
          }

          .metric-value {
            color: var(--text);
            font-size: 1.02rem;
            font-weight: 700;
            text-align: right;
          }

          .status-ok {
            color: var(--green);
          }

          .status-warn {
            color: var(--amber);
          }

          .status-bad {
            color: var(--red);
          }

          .progress-track {
            width: 100%;
            height: 16px;
            border-radius: 999px;
            background: var(--track);
            overflow: hidden;
            margin-top: 0.35rem;
          }

          .progress-fill {
            height: 100%;
            border-radius: 999px;
          }

          .muted-note {
            color: var(--muted);
            font-size: 0.92rem;
          }

          .history-toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin: 0.35rem 0 0.85rem;
          }

          .history-title {
            font-size: 1.2rem;
            font-weight: 700;
            margin: 0;
          }

          .history-subtitle {
            color: var(--muted);
            font-size: 0.92rem;
            margin-top: 0.25rem;
          }

          .stButton > button {
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            background: rgba(255, 255, 255, 0.04);
            color: var(--text);
            padding: 0.55rem 1rem;
          }

          div[data-testid="stRadio"] > div {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 999px;
            padding: 0.2rem 0.45rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=30, show_spinner=False)
def load_usage() -> Tuple[str, str, Dict[str, Any]]:
    usage_url, raw_body, data = fetch_usage_snapshot()
    save_history_snapshot_if_changed(data, source="ui")
    return usage_url, raw_body, data


def clamp_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 100.0))
    return 0.0


def status_badge(limit: Dict[str, Any]) -> Tuple[str, str]:
    allowed = limit.get("allowed")
    limit_reached = limit.get("limit_reached")
    if allowed is False:
        return "不可用", "status-bad"
    if limit_reached:
        return "已达上限", "status-warn"
    if allowed:
        return "可用", "status-ok"
    return "未知", ""


def progress_bar(percent: Any, color: str) -> str:
    bounded = clamp_percent(percent)
    return (
        '<div class="progress-track">'
        f'<div class="progress-fill" style="width:{bounded:.0f}%;background:{color};"></div>'
        "</div>"
    )


def window_section(title: str, window: Dict[str, Any], color: str) -> str:
    used_percent = clamp_percent(window.get("used_percent"))
    span = format_window_span(window.get("limit_window_seconds"))
    reset_after = format_remaining(window.get("reset_after_seconds"))
    reset_at = format_reset_at(window.get("reset_at"))
    return html_block(
        f"""
        <div class="window-block">
          <div class="window-title">{escape(title)}（{escape(span)}）</div>
          <div class="window-meta">
            <div class="window-used">已使用 {used_percent:.0f}%</div>
            <div class="window-reset">{escape(reset_after)}</div>
          </div>
          {progress_bar(used_percent, color)}
          <div class="window-foot">重置时间 {escape(reset_at)}</div>
        </div>
        """
    )


def metric_rows(rows: Iterable[Tuple[str, str, str]]) -> str:
    parts = []
    for label, value, value_class in rows:
        klass = f"metric-value {value_class}".strip()
        parts.append(
            f'<div class="metric-row"><div class="metric-label">{escape(label)}</div>'
            f'<div class="{klass}">{value}</div></div>'
        )
    return "".join(parts)


def render_card(title: str, inner_html: str) -> None:
    st.markdown(
        html_block(
            f"""
            <section class="card">
              <div class="card-title">{escape(title)}</div>
              {inner_html}
            </section>
            """
        ),
        unsafe_allow_html=True,
    )


def pair_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]} / {value[1]}"
    return "未知"


def format_history_status_timestamp(unix_ts: Any) -> str:
    if not isinstance(unix_ts, (int, float)):
        return "尚无"
    return datetime.fromtimestamp(unix_ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_history_result(result: str) -> str:
    mapping = {
        "saved": "有变化已保存",
        "unchanged": "无变化未保存",
        "error": "采样失败",
        "no_data": "无可保存数据",
    }
    return mapping.get(result, "尚未采样")


def history_chart(frame: pd.DataFrame, color_map: Dict[str, str]) -> alt.Chart:
    color_domain = [key for key in color_map if key in set(frame["series_label"].tolist())]
    color_range = [color_map[key] for key in color_domain]
    base = alt.Chart(frame).encode(
        x=alt.X("sampled_at:T", title="时间"),
        y=alt.Y("used_percent:Q", title="已用 %", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color(
            "series_label:N",
            title="序列",
            scale=alt.Scale(domain=color_domain, range=color_range),
        ),
        tooltip=[
            alt.Tooltip("sampled_at:T", title="采样时间"),
            alt.Tooltip("series_label:N", title="序列"),
            alt.Tooltip("used_percent:Q", title="已用 %", format=".0f"),
        ],
    )
    line = base.mark_line(strokeWidth=3)
    points = base.mark_circle(size=60, opacity=1)
    return (line + points).properties(height=260)


def render_history_block(
    title: str,
    frame: pd.DataFrame,
    color_map: Dict[str, str],
    empty_message: str,
) -> None:
    st.subheader(title)
    if frame.empty or frame["sampled_at"].nunique() < 2:
        st.info(empty_message)
        return

    sample_count = int(frame["sampled_at"].nunique())
    latest = frame["sampled_at"].max()
    st.caption(
        f"最近采样 {latest.strftime('%Y-%m-%d %H:%M:%S')} · {sample_count} 次采样 · {len(frame)} 条样本"
    )
    st.altair_chart(history_chart(frame, color_map), use_container_width=True)


def render_history_section() -> None:
    st.markdown(
        html_block(
            """
            <div class="history-toolbar">
              <div>
                <div class="history-title">历史趋势</div>
                <div class="history-subtitle">历史数据来自本地采样；首次打开不会立刻形成曲线。</div>
              </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    status = load_history_status()

    range_key = st.radio(
        "历史时间范围",
        options=HISTORY_RANGE_OPTIONS,
        horizontal=True,
        index=1,
        label_visibility="collapsed",
        key="history_range",
    )
    history_frame = load_history_samples(range_key)

    core_frame = history_frame[history_frame["metric_group"] == "rate_limit"].copy()
    render_history_block(
        "配额使用趋势",
        core_frame,
        {"主窗口": "#79a8df", "周窗口": "#f5a623"},
        "历史样本不足，打开页面或刷新后会逐步积累。",
    )

    review_frame = history_frame[history_frame["metric_group"] == "code_review_rate_limit"].copy()
    render_history_block(
        "Code Review 趋势",
        review_frame,
        {"Code Review": "#7cc045"},
        "历史样本不足，打开页面或刷新后会逐步积累。",
    )

    with st.expander("额外配额趋势", expanded=False):
        additional_frame = history_frame[history_frame["metric_group"] == "additional_rate_limit"].copy()
        if additional_frame.empty:
            st.info("暂无额外配额历史样本。")
        else:
            for (limit_name, metered_feature), group in additional_frame.groupby(
                ["limit_name", "metered_feature"], sort=True
            ):
                label = str(limit_name or "附加配额")
                if metered_feature:
                    label = f"{label} · {metered_feature}"
                render_history_block(
                    label,
                    group.copy(),
                    {"主窗口": "#79a8df", "周窗口": "#7cc045"},
                    "历史样本不足，打开页面或刷新后会逐步积累。",
                )

    status_rows = [
        (
            "最近检查",
            format_history_status_timestamp(status.get("last_checked_at")),
            "",
        ),
        (
            "最近保存",
            format_history_status_timestamp(status.get("last_saved_at")),
            "",
        ),
        (
            "最近结果",
            escape(format_history_result(str(status.get("last_result") or ""))),
            "",
        ),
        (
            "最近插入条数",
            str(status.get("last_inserted_count", 0)),
            "",
        ),
        (
            "历史数据库",
            escape(str(history_db_path())),
            "",
        ),
    ]
    if status.get("last_error"):
        status_rows.append(("最近错误", escape(str(status["last_error"])), "status-warn"))
    with st.expander("采集状态", expanded=False):
        render_card("采集状态", metric_rows(status_rows))


def render_usage_detail(rate_limit: Dict[str, Any]) -> None:
    sections = []
    primary = rate_limit.get("primary_window")
    secondary = rate_limit.get("secondary_window")
    if isinstance(primary, dict):
        sections.append(window_section("主窗口", primary, "var(--blue)"))
    if isinstance(secondary, dict):
        sections.append(window_section("周窗口", secondary, "var(--amber)"))
    if not sections:
        sections.append('<div class="muted-note">暂无配额使用数据。</div>')
    render_card("配额使用详情", "".join(sections))


def render_code_review(rate_limit: Dict[str, Any]) -> None:
    primary = rate_limit.get("primary_window") if isinstance(rate_limit, dict) else None
    status_text, status_class = status_badge(rate_limit if isinstance(rate_limit, dict) else {})
    used_percent = clamp_percent(primary.get("used_percent")) if isinstance(primary, dict) else 0
    cycle = format_window_span(primary.get("limit_window_seconds")) if isinstance(primary, dict) else "未知"
    rows = metric_rows(
        [
            ("状态", escape(status_text), status_class),
            ("周配额已用", f"{used_percent:.0f}%", ""),
            ("重置周期", escape(cycle), ""),
        ]
    )
    html = rows + progress_bar(used_percent, "var(--green)")
    render_card("Code Review 配额", html)


def render_additional_limits(items: Any) -> None:
    if not isinstance(items, list) or not items:
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        title = f"{item.get('limit_name') or '附加'} 额外配额"
        metered_feature = item.get("metered_feature") or "-"
        limit = item.get("rate_limit") if isinstance(item.get("rate_limit"), dict) else {}
        primary = limit.get("primary_window") if isinstance(limit.get("primary_window"), dict) else {}
        secondary = limit.get("secondary_window") if isinstance(limit.get("secondary_window"), dict) else {}
        status_text, status_class = status_badge(limit)
        primary_label = format_window_span(primary.get("limit_window_seconds"))
        secondary_label = format_window_span(secondary.get("limit_window_seconds"))
        weekly_percent = clamp_percent(secondary.get("used_percent"))
        rows = metric_rows(
            [
                ("功能代号", escape(str(metered_feature)), ""),
                ("状态", escape(status_text), status_class),
                ("主窗口已用（%s）" % escape(primary_label), f"{clamp_percent(primary.get('used_percent')):.0f}%", ""),
                ("周窗口已用（%s）" % escape(secondary_label), f"{weekly_percent:.0f}%", ""),
            ]
        )
        html = rows + progress_bar(weekly_percent, "var(--green)")
        render_card(title, html)


def render_credits(credits: Dict[str, Any]) -> None:
    rows = metric_rows(
        [
            ("余额", escape(str(credits.get("balance", "0"))), ""),
            ("无限积分", "是" if credits.get("unlimited") else "否", ""),
            ("本地消息估算", escape(pair_text(credits.get("approx_local_messages"))), ""),
            ("云端消息估算", escape(pair_text(credits.get("approx_cloud_messages"))), ""),
        ]
    )
    render_card("积分余额", rows)


def render_page(data: Dict[str, Any], usage_url: str, raw_body: str) -> None:
    plan = str(data.get("plan_type") or "unknown").upper()
    email = str(data.get("email") or "-")
    refreshed_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    github_url = "https://github.com/onewesong/codex-usage-ui"
    left_col, right_col = st.columns([1.4, 1])
    with left_col:
        st.markdown(
            html_block(
                """
                <div>
                  <div class="eyebrow">Codex Usage</div>
                  <div class="page-title">配额看板</div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with right_col:
        st.markdown(
            html_block(
                f"""
                <div class="toolbar-meta">
                  <div class="toolbar-links">
                    <a
                      class="github-link"
                      href="{escape(github_url)}"
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="Open GitHub repository"
                      title="Open GitHub repository"
                    >
                      <svg viewBox="0 0 16 16" aria-hidden="true">
                        <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38
                        0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
                        -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.5-1.07
                        -1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12
                        0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12
                        .51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48
                        0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z"></path>
                      </svg>
                    </a>
                    <span class="pill">Plan: {escape(plan)}</span>
                    <span class="pill">{escape(email)}</span>
                  </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
        refresh_text_col, refresh_button_col = st.columns([12, 1], gap="small")
        with refresh_text_col:
            st.markdown(
                html_block(
                    f"""
                    <div class="refresh-meta">
                      <span class="refresh-text">最后刷新 {escape(refreshed_at)}</span>
                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )
        with refresh_button_col:
            if st.button("↻", key="refresh_top", help="刷新数据", type="tertiary"):
                load_usage.clear()
                st.rerun()

    overview_tab, history_tab, raw_tab = st.tabs(
        ["实时总览", "历史趋势", "原始 JSON"]
    )

    with overview_tab:
        render_usage_detail(data.get("rate_limit") if isinstance(data.get("rate_limit"), dict) else {})
        render_code_review(
            data.get("code_review_rate_limit")
            if isinstance(data.get("code_review_rate_limit"), dict)
            else {}
        )
        additional_items = data.get("additional_rate_limits")
        if isinstance(additional_items, list) and additional_items:
            render_additional_limits(additional_items)
        render_credits(data.get("credits") if isinstance(data.get("credits"), dict) else {})

    with history_tab:
        render_history_section()

    with raw_tab:
        st.caption(f"来源: `{usage_url}`")
        st.code(raw_body, language="json")


def main() -> None:
    inject_css()
    try:
        usage_url, raw_body, data = load_usage()
    except Exception as exc:
        st.error(f"加载 Codex 配额失败: {exc}")
        st.info("请先执行 `codex login chatgpt`，并确认本机能访问 ChatGPT 后端。")
        return

    render_page(data, usage_url, raw_body)


if __name__ == "__main__":
    main()
