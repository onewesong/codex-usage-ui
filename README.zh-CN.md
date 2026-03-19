<div align="center">

# codex-usage-ui

基于 Streamlit 的本地 Codex 配额看板，支持 CLI 输出和按变化保存的历史采集。

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/streamlit-1.42%2B-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/history-sqlite-003B57?logo=sqlite&logoColor=white)
![GitHub Repo stars](https://img.shields.io/github/stars/onewesong/codex-usage-ui?style=flat)
![GitHub last commit](https://img.shields.io/github/last-commit/onewesong/codex-usage-ui)

[English](README.md) | 简体中文

</div>

<img alt="codex-usage-ui dashboard" src="https://github.com/user-attachments/assets/bc20cd26-4e8c-467a-bd11-eb7b32c0f088" />

`codex-usage-ui` 会读取本机 Codex / ChatGPT 登录态，请求 Codex usage 接口，并展示当前限额和本地历史趋势图表。

## 功能特性

- 基于 Streamlit 的看板，包含 `实时总览`、`历史趋势`、`原始 JSON`
- 使用本地 SQLite 存储历史数据，并按变化落点
- 支持独立采集器常驻后台采样
- CLI 支持带 Unicode 进度条的人类可读输出
- 支持自定义鉴权文件和历史数据库路径
- 不依赖额外后端服务

## 安装

环境要求：

- Python 3.9+
- 本机已有可用的 Codex / ChatGPT 登录态

如未登录可先执行：

```bash
codex login chatgpt
```

克隆并启动：

```bash
git clone https://github.com/onewesong/codex-usage-ui.git
cd codex-usage-ui
./run.sh
```

首次启动时 `run.sh` 会自动：

1. 创建 `.venv`
2. 安装 `requirements.txt`
3. 启动 Streamlit，默认地址为 `http://127.0.0.1:8501`

如端口冲突可改用：

```bash
PORT=8511 ./run.sh
```

## 快速开始

启动看板：

```bash
./run.sh
```

启动独立采集器：

```bash
./run-collector.sh
```

只采集一次后退出：

```bash
./run-collector.sh --once
```

输出人类可读摘要：

```bash
python3 get-codex-usage.py --human
```

只输出原始 JSON：

```bash
python3 get-codex-usage.py --json-only
```

## 历史采集

历史趋势来自本地持续采样，并不是服务端提供的历史接口。

如果你希望长期观察曲线，建议使用独立采集器常驻运行：

```bash
./run-collector.sh
```

默认行为：

- 启动后立即采样一次
- 默认每 `300` 秒采样一次
- 只有快照发生变化时才保存新的数据点
- 即使没有新数据点，也会持续检查

以下字段用于判断某条时间序列是否发生变化：

- `used_percent`
- `allowed`
- `limit_reached`
- `reset_at`

自定义采样间隔：

```bash
./run-collector.sh --interval-seconds 60
```

单次执行并输出 JSON：

```bash
./run-collector.sh --once --json
```

## CLI

人类可读输出：

```bash
python3 get-codex-usage.py --human
```

示例：

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

原始 JSON：

```bash
python3 get-codex-usage.py --json-only
```

CLI 本身不会常驻采集历史数据；如果要长期追踪，请使用 `run-collector.sh`。

## 环境变量

- `CODEX_AUTH_PATH`：覆盖默认鉴权文件路径 `~/.codex/auth.json`
- `CODEX_HOME`：覆盖默认 Codex 目录 `~/.codex`
- `PORT`：覆盖默认 Streamlit 端口 `8501`
- `CODEX_USAGE_DB_PATH`：覆盖默认历史数据库路径 `~/.codex-usage-ui/history.sqlite3`

示例：

```bash
CODEX_AUTH_PATH=/path/to/auth.json ./run.sh
```

```bash
CODEX_HOME=/path/to/.codex CODEX_USAGE_DB_PATH=/path/to/history.sqlite3 ./run-collector.sh
```

## 工作原理

1. 优先从 `CODEX_AUTH_PATH` 读取鉴权文件，否则回退到 `~/.codex/auth.json`
2. 从 `CODEX_HOME/config.toml` 或 `~/.codex/config.toml` 读取配置
3. 请求 usage 接口
4. 将快照归一化为时间序列
5. 与每条序列最近一次保存的数据做比较
6. 只有关键字段变化时才写入新的历史点
7. 在 Streamlit 中渲染实时状态和历史曲线

核心文件：

- `codex_usage.py`：鉴权读取、HTTP 请求、响应格式化
- `history_store.py`：SQLite 持久化与按变化落点
- `codex_usage_app.py`：Streamlit UI
- `collect_history.py`：独立采集器
- `get-codex-usage.py`：CLI 入口

## 说明

- 这个项目依赖本机已有的 Codex / ChatGPT 登录态
- 历史曲线在刚开始时通常点数较少，需要后续采样逐步积累
- UI 也会写历史，但要稳定持续采集，独立采集器更合适
