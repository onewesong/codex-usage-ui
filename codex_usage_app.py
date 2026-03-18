#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from html import escape
from textwrap import dedent
from typing import Any, Dict, Iterable, Tuple

import streamlit as st

from codex_usage import (
    fetch_usage_snapshot,
    format_remaining,
    format_reset_at,
    format_window_span,
)


st.set_page_config(page_title="Codex 配额看板", layout="wide")


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

          .pill {
            display: inline-block;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 999px;
            padding: 0.32rem 0.75rem;
            margin-left: 0.45rem;
            color: var(--text);
            background: rgba(255, 255, 255, 0.03);
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

          .stButton > button {
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            background: rgba(255, 255, 255, 0.04);
            color: var(--text);
            padding: 0.55rem 1rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=30, show_spinner=False)
def load_usage() -> Tuple[str, str, Dict[str, Any]]:
    return fetch_usage_snapshot()


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

    st.markdown(
        html_block(
            f"""
        <div class="topbar">
          <div>
            <div class="eyebrow">Codex Usage</div>
            <div class="page-title">配额看板</div>
          </div>
          <div class="toolbar-meta">
            <span class="pill">Plan: {escape(plan)}</span>
            <span class="pill">{escape(email)}</span>
            <div style="margin-top:0.55rem;">最后刷新 {escape(refreshed_at)}</div>
          </div>
        </div>
        """
        ),
        unsafe_allow_html=True,
    )

    render_usage_detail(data.get("rate_limit") if isinstance(data.get("rate_limit"), dict) else {})
    render_code_review(
        data.get("code_review_rate_limit")
        if isinstance(data.get("code_review_rate_limit"), dict)
        else {}
    )
    render_additional_limits(data.get("additional_rate_limits"))
    render_credits(data.get("credits") if isinstance(data.get("credits"), dict) else {})

    with st.expander("查看原始 JSON"):
        st.caption(f"来源: `{usage_url}`")
        st.code(raw_body, language="json")


def main() -> None:
    inject_css()
    refresh_col, _ = st.columns([1, 7])
    with refresh_col:
        if st.button("刷新数据", use_container_width=True):
            load_usage.clear()
            st.rerun()

    try:
        usage_url, raw_body, data = load_usage()
    except Exception as exc:
        st.error(f"加载 Codex 配额失败: {exc}")
        st.info("请先执行 `codex login chatgpt`，并确认本机能访问 ChatGPT 后端。")
        return

    render_page(data, usage_url, raw_body)


if __name__ == "__main__":
    main()
