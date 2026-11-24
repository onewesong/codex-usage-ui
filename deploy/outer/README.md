# r9s-outer 部署

项目路径为 `/home/cpa/codex-usage-ui`，运行用户为 `cpa`。UI 只监听 `127.0.0.1:8501`，`codex-usage.outer.r9s.net` 由现有 Nginx 和 r9s-access 提供 HTTPS、GitHub 认证与 WebSocket 代理。

`fetch_cpa_usage.py` 从 `CPA_MANAGEMENT_KEY_FILE` 读取现有管理密钥，通过本机 `127.0.0.1:8317` 的 `/v0/management/auth-files` 枚举 Codex 账号，再逐账号调用 `/v0/management/api-call` 获取配额。账号 token 由 CPA 注入，面板不读取认证文件或输出 token；管理密钥不写进环境变量、Git 或日志。CPA 管理密钥文件应由 `cpa` 所有并设为 `0600`。

多个账号通过页面顶部的账号选择框切换，配额及历史按账号隔离。一个账号读取失败时显示该账号错误，其他账号继续可用。同一 ChatGPT 账号的重复凭据仅展示一次。单账号的原始 usage JSON 仍兼容原有采集方式。

部署前准备 Python 3.12、python3.12-venv，克隆项目并创建 `.venv`、安装 `requirements.txt`。安装用户级服务：

```bash
# 以下命令在 cpa 用户下执行。
mkdir -p ~/.config/codex-usage-ui ~/.config/systemd/user ~/.local/share/codex-usage-ui
chmod 700 ~/.config/codex-usage-ui ~/.local/share/codex-usage-ui
cp deploy/outer/service.env.example ~/.config/codex-usage-ui/service.env
chmod 600 ~/.config/codex-usage-ui/service.env
cp deploy/outer/codex-usage-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now codex-usage-ui.service codex-usage-collector.service
```

管理员执行 `loginctl enable-linger cpa`，确保无登录会话时仍可开机启动。采集器由独立 systemd 服务每 300 秒采集，UI 自动后台采集功能关闭，避免重复进程。历史保存于 `/home/cpa/.local/share/codex-usage-ui/history.sqlite3`，重启和更新不删除数据库。

在切换入口前，确认本机 `http://127.0.0.1:8501/_stcore/health` 返回 `ok`，运行 `python -m unittest discover -s tests -v`，并确认采集器已成功写入各账号的样本。备份 `/etc/nginx/conf.d/r9s-codex-outer.r9s.net.conf` 后，将本目录 `nginx.conf` 安装到该位置，执行 `nginx -t` 再 reload。失败则恢复备份并 reload，原内网服务继续保留。

验收未登录访问首页、`/_stcore/stream` 均跳转 Access；登录后页面正常展示账号选择、配额与历史，WebSocket 可建立。管理命令使用 `systemctl --user status/restart` 与 `journalctl --user -u codex-usage-ui -u codex-usage-collector`。
