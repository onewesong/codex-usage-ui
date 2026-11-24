<div align="center">

# codex-usage-ui

Local Codex usage dashboard with Streamlit, CLI output, and change-based history collection.

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/streamlit-1.42%2B-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/history-sqlite-003B57?logo=sqlite&logoColor=white)
![GitHub Repo stars](https://img.shields.io/github/stars/onewesong/codex-usage-ui?style=flat)
![GitHub last commit](https://img.shields.io/github/last-commit/onewesong/codex-usage-ui)
<a href="https://llmapis.com?source=https%3A%2F%2Fgithub.com%2Fonewesong%2Fcodex-usage-ui" target="_blank"><img src="https://llmapis.com/api/badge/onewesong/codex-usage-ui" alt="LLMAPIS" width="20" /></a>


English | [简体中文](README.zh-CN.md)

</div>

<img alt="codex-usage-ui dashboard" src="https://github.com/user-attachments/assets/bc20cd26-4e8c-467a-bd11-eb7b32c0f088" />

`codex-usage-ui` reads your local Codex / ChatGPT auth state, fetches usage data from the Codex usage endpoint, and renders a local dashboard for current limits and history charts.

## Features

- Streamlit dashboard with `实时总览`, `历史趋势`, and `原始 JSON` tabs
- local SQLite history storage with change-based sampling
- auto collector started by `run.sh` for interval-based background sampling
- standalone collector for long-running background collection
- human-readable CLI summary with Unicode progress bars
- support for custom auth and history database paths
- multi-account snapshots with account selection, independent history, and per-account errors
- no external backend required

## Installation

Requirements:

- Python 3.9+
- a valid local Codex / ChatGPT login

Login first if needed:

```bash
codex login chatgpt
```

Clone and start:

```bash
git clone https://github.com/onewesong/codex-usage-ui.git
cd codex-usage-ui
./run.sh
```

On first run, `run.sh` will:

1. create `.venv`
2. install `requirements.txt`
3. start Streamlit on `http://127.0.0.1:8501`

Use a different port if needed:

```bash
PORT=8511 ./run.sh
```

## Quick Start

Start the dashboard:

```bash
./run.sh
```

From this version on, running `./run.sh` will automatically start the background collector, so you do not need to open the page first.

Start the standalone collector:

```bash
./run-collector.sh
```

Run one collection cycle and exit:

```bash
./run-collector.sh --once
```

Print a human-readable summary:

```bash
python3 get-codex-usage.py --human
```

Print raw JSON only:

```bash
python3 get-codex-usage.py --json-only
```

## History Collection

History charts are built from local samples, not from a server-side history API.

By default, running `./run.sh` will start a background collector automatically.

For long-running tracking, you can still use the standalone collector if you prefer:

```bash
./run-collector.sh
```

Default behavior:

- run once immediately after startup
- collect every `300` seconds by default
- save a new data point only when the snapshot changes
- keep checking even if no new point is saved
- `History Trend -> 采集状态` shows the auto-collector state, PID, log path, and latest source
- collection starts as soon as `./run.sh` is running, even before any browser session opens

The following fields are used to decide whether a series changed:

- `used_percent`
- `allowed`
- `limit_reached`
- `reset_at`

Run with a custom interval:

```bash
./run-collector.sh --interval-seconds 60
```

Run once and emit JSON:

```bash
./run-collector.sh --once --json
```

## CLI

Human-readable output:

```bash
python3 get-codex-usage.py --human
```

Example:

```text
GET https://chatgpt.com/backend-api/wham/usage
订阅计划: pro

[配额使用详情]
- 主窗口（5小时）
  已使用   25%
  进度条   █████░░░░░░░░░░░░░░░ 25%
  重置剩余  约3小时后重置
  重置时间  2026-03-19 00:16:06
```

Raw JSON:

```bash
python3 get-codex-usage.py --json-only
```

The CLI does not continuously collect history by itself. Use `run-collector.sh` for long-running tracking.

## Environment Variables

- `CODEX_AUTH_PATH`: override the default auth file path instead of `~/.codex/auth.json`
- `CODEX_HOME`: override the default Codex home directory instead of `~/.codex`
- `PORT`: override the default Streamlit port `8501`
- `CODEX_USAGE_DB_PATH`: override the default history database path instead of `~/.codex-usage-ui/history.sqlite3`
- `CODEX_USAGE_AUTO_COLLECTOR`: enable or disable the background collector started by `run.sh`, default `1`
- `CODEX_USAGE_AUTO_COLLECTOR_INTERVAL_SECONDS`: interval for the auto collector, default `300`
- `CODEX_USAGE_FETCH_SCRIPT`: custom usage-fetch script (or command with arguments). When set, its stdout is used instead of local auth and the default usage endpoint.

The custom script must write a usage JSON object or a multi-account envelope (see below) to stdout; write diagnostics to stderr. This applies to the Web UI, CLI, and history collector.

```bash
CODEX_USAGE_FETCH_SCRIPT="/opt/scripts/fetch-codex-usage.sh" ./run.sh
```

### Multiple accounts

Any custom fetcher can supply multiple accounts without coupling the dashboard to a provider or deployment. Wrap the usual upstream responses in an `accounts` array:

```json
{
  "accounts": [
    {
      "account_id": "account-a",
      "email": "alice@example.com",
      "plan_type": "plus",
      "rate_limit": {
        "allowed": true,
        "limit_reached": false,
        "primary_window": {"used_percent": 25, "limit_window_seconds": 18000}
      }
    },
    {"account_id": "account-b", "email": "bob@example.com", "error": "Quota service unavailable"}
  ]
}
```

- Each entry requires a stable, unique, nonempty string `account_id`. Do not use list positions or access tokens as identifiers. `email` and `plan_type` are optional display fields.
- A successful entry contains the usual upstream usage fields. A failed entry can provide a nonempty `error` string; other accounts remain available, and failed entries do not write quota samples.
- The UI selects accounts by ID and filters history to the selected account. Reordering the source list does not switch the selected account. A failed account can retry and still view its previous history.
- `--human` prints a separate section for each account. The background collector samples every successful account; if all accounts fail, it records a failed check. An empty `accounts` array means no accounts and produces no samples.
- Existing single-account responses and SQLite files continue to work. No schema rewrite is required; existing rows keep their recorded account IDs. History without an account ID is retained but is not automatically assigned to a newly identified account.

To preview two accounts with **static example data**:

```bash
CODEX_USAGE_FETCH_SCRIPT="cat examples/multi-account-snapshot.json" ./run.sh
CODEX_USAGE_FETCH_SCRIPT="cat examples/multi-account-snapshot.json" python3 get-codex-usage.py --human
```

For live data, replace the command with your own fetcher. Keep credentials and private auth files outside the repository; return usage fields only, never tokens. The existing 30-second command timeout applies to the complete snapshot.

Examples:

```bash
CODEX_AUTH_PATH=/path/to/auth.json ./run.sh
```

```bash
CODEX_HOME=/path/to/.codex CODEX_USAGE_DB_PATH=/path/to/history.sqlite3 ./run-collector.sh
```

```bash
CODEX_USAGE_AUTO_COLLECTOR=0 ./run.sh
```

```bash
CODEX_USAGE_AUTO_COLLECTOR_INTERVAL_SECONDS=60 ./run.sh
```

## Systemd Services

To run the dashboard and collector in the background with systemd:

```bash
sudo ./systemd/install-systemd.sh
```

This installs and starts:

- `codex-usage-ui.service`: Streamlit dashboard on port `18081` by default
- `codex-usage-collector.service`: history collector, sampling every `300` seconds by default

Useful commands:

```bash
systemctl status codex-usage-ui.service codex-usage-collector.service
journalctl -u codex-usage-ui.service -f
journalctl -u codex-usage-collector.service -f
systemctl restart codex-usage-ui.service
systemctl disable --now codex-usage-ui.service codex-usage-collector.service
```

Override defaults during installation:

```bash
sudo PORT=8511 COLLECT_INTERVAL_SECONDS=60 ./systemd/install-systemd.sh
```

Set a specific service user or auth/database paths:

```bash
sudo SERVICE_USER="$USER" CODEX_HOME="$HOME/.codex" CODEX_USAGE_DB_PATH="$HOME/.codex-usage-ui/history.sqlite3" ./systemd/install-systemd.sh
```

## How It Works

1. Load auth from `CODEX_AUTH_PATH` or `~/.codex/auth.json`
2. Load config from `CODEX_HOME/config.toml` or `~/.codex/config.toml`
3. Request the usage endpoint
4. Normalize snapshot data into time series
5. Compare each series with the latest saved sample
6. Write a new point only when the key fields changed
7. Render current status and local history charts in Streamlit

Core files:

- `codex_usage.py`: auth loading, HTTP requests, response formatting
- `history_store.py`: SQLite persistence and change-based history writes
- `codex_usage_app.py`: Streamlit UI
- `collect_history.py`: standalone collector
- `get-codex-usage.py`: CLI entrypoint

## Notes

- this project relies on your local Codex / ChatGPT login state
- the first history chart usually has too few points until more samples accumulate
- the UI can write history, and `run.sh` now also starts a background collector by default
- if you prefer a separately managed process, disable auto collection and keep using `run-collector.sh`
