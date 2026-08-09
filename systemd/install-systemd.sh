#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn "${SERVICE_USER}" 2>/dev/null || id -gn)}"
SERVICE_HOME="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"
PORT="${PORT:-18081}"
COLLECT_INTERVAL_SECONDS="${COLLECT_INTERVAL_SECONDS:-300}"
ENABLE_SERVICES="${ENABLE_SERVICES:-1}"
RELOAD_SYSTEMD="${RELOAD_SYSTEMD:-1}"

if [ -z "${SERVICE_HOME}" ]; then
  echo "Unable to resolve home directory for user: ${SERVICE_USER}" >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root, for example: sudo $0" >&2
  exit 1
fi

if [ ! -x "${ROOT_DIR}/run.sh" ] || [ ! -x "${ROOT_DIR}/run-collector.sh" ]; then
  echo "Missing executable run.sh or run-collector.sh in ${ROOT_DIR}" >&2
  exit 1
fi

CODEX_HOME_VALUE="${CODEX_HOME:-${SERVICE_HOME}/.codex}"
CODEX_AUTH_PATH_VALUE="${CODEX_AUTH_PATH:-${CODEX_HOME_VALUE}/auth.json}"
CODEX_USAGE_DB_PATH_VALUE="${CODEX_USAGE_DB_PATH:-${SERVICE_HOME}/.codex-usage-ui/history.sqlite3}"

install -d "${SYSTEMD_DIR}"

cat >"${SYSTEMD_DIR}/codex-usage-ui.service" <<EOF
[Unit]
Description=Codex Usage UI
Documentation=https://github.com/onewesong/codex-usage-ui
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment=PORT=${PORT}
Environment=CODEX_HOME=${CODEX_HOME_VALUE}
Environment=CODEX_AUTH_PATH=${CODEX_AUTH_PATH_VALUE}
Environment=CODEX_USAGE_DB_PATH=${CODEX_USAGE_DB_PATH_VALUE}
Environment=CODEX_USAGE_AUTO_COLLECTOR=0
Environment=PYTHONUNBUFFERED=1
# Environment=CODEX_USAGE_FETCH_SCRIPT=/root/tools/fetch-codex-usage.sh
ExecStart=${ROOT_DIR}/run.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat >"${SYSTEMD_DIR}/codex-usage-collector.service" <<EOF
[Unit]
Description=Codex Usage History Collector
Documentation=https://github.com/onewesong/codex-usage-ui
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment=CODEX_HOME=${CODEX_HOME_VALUE}
Environment=CODEX_AUTH_PATH=${CODEX_AUTH_PATH_VALUE}
Environment=CODEX_USAGE_DB_PATH=${CODEX_USAGE_DB_PATH_VALUE}
Environment=PYTHONUNBUFFERED=1
# Environment=CODEX_USAGE_FETCH_SCRIPT=/root/tools/fetch-codex-usage.sh
ExecStart=${ROOT_DIR}/run-collector.sh --interval-seconds ${COLLECT_INTERVAL_SECONDS} --source systemd_collector
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

if [ "${RELOAD_SYSTEMD}" = "1" ]; then
  systemctl daemon-reload
fi

if [ "${ENABLE_SERVICES}" = "1" ]; then
  systemctl enable --now codex-usage-ui.service codex-usage-collector.service
fi

echo "Installed:"
echo "  ${SYSTEMD_DIR}/codex-usage-ui.service"
echo "  ${SYSTEMD_DIR}/codex-usage-collector.service"
echo
echo "Useful commands:"
echo "  systemctl status codex-usage-ui.service codex-usage-collector.service"
echo "  journalctl -u codex-usage-ui.service -f"
echo "  journalctl -u codex-usage-collector.service -f"
