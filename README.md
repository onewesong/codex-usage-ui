# codex-usage-ui

一个基于 Streamlit 的 Codex 配额看板。

它会读取本机 `~/.codex/auth.json` 中缓存的 ChatGPT 登录信息，请求 Codex 使用量接口，并展示：

- 主窗口配额
- 周窗口配额
- Code Review 配额
- Additional rate limits
- Credits / 积分余额

界面默认是深色卡片样式，适合本地直接打开查看当前限额。

## 功能

- 一键启动 Streamlit 页面
- 自动创建本地虚拟环境并安装依赖
- 复用本机 `codex login chatgpt` 的登录态
- 支持按钮手动刷新
- 保留 CLI 方式输出 JSON 或人类可读摘要

## 目录结构

```text
codex-usage-ui/
├── .gitignore
├── README.md
├── codex_usage.py
├── codex_usage_app.py
├── get-codex-usage.py
├── requirements.txt
└── run.sh
```

## 环境要求

- Python 3.9+
- 已安装并登录 Codex CLI / ChatGPT：

```bash
codex login chatgpt
```

如果本机没有 `~/.codex/auth.json`，应用无法拉取配额数据。

## 快速开始

```bash
git clone <your-repo-url>
cd codex-usage-ui
./run.sh
```

首次启动会自动：

1. 创建 `.venv`
2. 安装 `requirements.txt`
3. 启动 Streamlit 服务

默认地址：

```text
http://127.0.0.1:8501
```

如果 `8501` 端口已被占用：

```bash
PORT=8511 ./run.sh
```

## CLI 用法

输出人类可读摘要：

```bash
./.venv/bin/python get-codex-usage.py --human
```

只输出原始 JSON：

```bash
./.venv/bin/python get-codex-usage.py --json-only
```

如果你不想先启动虚拟环境，也可以直接：

```bash
python3 get-codex-usage.py --json-only
```

## 工作原理

应用会：

1. 读取 `~/.codex/auth.json`
2. 从 `~/.codex/config.toml` 解析 `chatgpt_base_url`（如果存在）
3. 请求：
   - `https://chatgpt.com/backend-api/wham/usage`
   - 或兼容的 `/api/codex/usage`
4. 将返回结果渲染成 Streamlit 看板

核心逻辑在：

- `codex_usage.py`：鉴权、请求、时间格式化
- `codex_usage_app.py`：Streamlit UI
- `get-codex-usage.py`：CLI 入口

## 注意事项

- 本项目不会帮你登录，必须先执行 `codex login chatgpt`
- 该工具依赖本机已有登录态，不适合部署到无登录信息的纯服务器
- 页面中的数据来自 ChatGPT/Codex 后端接口，字段结构未来可能变化
- `.venv/`、`__pycache__/` 等本地文件已在 `.gitignore` 中忽略

## 发布到 GitHub

如果你已经登录 `gh`：

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create codex-usage-ui --private --source=. --remote=origin --push
```

如果你想发布为公开仓库，把 `--private` 改成 `--public`。
