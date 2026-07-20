#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVICE_NAME=otveto4ka-compose.service
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
DOCKER_BIN=$(command -v docker || true)

if [ -z "$DOCKER_BIN" ]; then
    echo "Docker не найден."
    exit 1
fi
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Не найден $PROJECT_DIR/.env"
    exit 1
fi

cd "$PROJECT_DIR"
"$DOCKER_BIN" compose config --quiet

UNIT_FILE=$(mktemp)
trap 'rm -f "$UNIT_FILE"' EXIT

cat >"$UNIT_FILE" <<EOF
[Unit]
Description=OtvetO4ka Telegram bot and API
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=$DOCKER_BIN compose up -d --remove-orphans
ExecReload=$DOCKER_BIN compose up -d --remove-orphans
ExecStop=$DOCKER_BIN compose stop
TimeoutStartSec=0
TimeoutStopSec=180

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$UNIT_FILE" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now docker
sudo systemctl enable --now "$SERVICE_NAME"

echo
echo "Автозапуск установлен:"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
echo
"$DOCKER_BIN" compose ps
