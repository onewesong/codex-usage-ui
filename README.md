# codex-usage-ui
<img width="2098" height="1684" alt="image" src="https://github.com/user-attachments/assets/bc20cd26-4e8c-467a-bd11-eb7b32c0f088" />

一个基于 Streamlit 的 Codex 配额看板。

它会读取本机 Codex/ChatGPT 登录态，请求 Codex 使用量接口，并展示：

- 主窗口配额
- 周窗口配额
- Code Review 配额
- Additional rate limits
- Credits / 积分余额

界面默认是深色卡片样式，适合本地直接打开查看当前限额；同时保留 CLI 模式，方便在终端里快速查看。

## 功能

- 一键启动 Streamlit 页面
- 自动创建本地虚拟环境并安装依赖
- 复用本机 `codex login chatgpt` 的登录态
- 支持按钮手动刷新
- 支持 `CODEX_AUTH_PATH` 覆盖默认 `auth.json`
- 保留 CLI 方式输出 JSON 或人类可读摘要
- CLI 摘要支持文本进度条，例如 `█████░░░░░░░░░░░░░`

## 仓库地址

```text
https://github.com/onewesong/codex-usage-ui
```

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

如果本机没有可用的登录态文件，应用无法拉取配额数据。

## 环境变量

`codex-usage-ui` 当前支持这些环境变量：

- `CODEX_AUTH_PATH`
  用于覆盖默认的 `~/.codex/auth.json`
- `CODEX_HOME`
  用于覆盖默认的 `~/.codex` 目录，程序会继续从这个目录查找 `config.toml`
- `PORT`
  用于覆盖 Streamlit 默认端口 `8501`

示例：

```bash
export CODEX_AUTH_PATH=/path/to/auth.json
export CODEX_HOME=/path/to/.codex
export PORT=8511
```

## 快速开始

```bash
git clone https://github.com/onewesong/codex-usage-ui.git
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

如果你要使用自定义 `auth.json`：

```bash
CODEX_AUTH_PATH=/path/to/auth.json ./run.sh
```

如果你还要覆盖 Codex 配置目录：

```bash
CODEX_HOME=/path/to/.codex ./run.sh
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

使用自定义鉴权文件：

```bash
CODEX_AUTH_PATH=/path/to/auth.json python3 get-codex-usage.py --human
```

示例输出：

```text
GET https://chatgpt.com/backend-api/wham/usage
订阅计划: pro

[配额使用详情]
- 主窗口（5小时）
  已使用   25%
  进度条   █████░░░░░░░░░░░░░░░ 25%
  重置剩余  约3小时后重置
  重置时间  2026-03-19 00:16:06
- 周窗口（7天）
  已使用   59%
  进度条   ████████████░░░░░░░░ 59%
  重置剩余  约7小时后重置
  重置时间  2026-03-19 04:05:12
```

## 工作原理

应用会：

1. 优先读取 `CODEX_AUTH_PATH` 指向的文件，否则读取 `~/.codex/auth.json`
2. 从 `CODEX_HOME/config.toml` 或 `~/.codex/config.toml` 解析 `chatgpt_base_url`（如果存在）
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
- 如果你不想使用默认的 `~/.codex/auth.json`，可以设置 `CODEX_AUTH_PATH`
- 如果你需要切换整套 Codex 配置目录，可以设置 `CODEX_HOME`
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
