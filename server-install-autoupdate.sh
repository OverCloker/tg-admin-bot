#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BRANCH=${1:-main}
INTERVAL=${AUTO_UPDATE_INTERVAL:-5min}
SERVICE_NAME=otveto4ka-auto-update.service
TIMER_NAME=otveto4ka-auto-update.timer
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
TIMER_PATH="/etc/systemd/system/$TIMER_NAME"

if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd not found"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "git not found"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Missing $PROJECT_DIR/.env"
    exit 1
fi

SERVICE_FILE=$(mktemp)
TIMER_FILE=$(mktemp)
trap 'rm -f "$SERVICE_FILE" "$TIMER_FILE"' EXIT

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=OtvetO4ka Git auto-update
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
ExecStart=/bin/sh $PROJECT_DIR/server-auto-update.sh $BRANCH
SyslogIdentifier=otveto4ka-auto-update
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
TimeoutStartSec=0
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Check GitHub and auto-update OtvetO4ka

[Timer]
OnBootSec=2min
OnUnitActiveSec=$INTERVAL
RandomizedDelaySec=30s
AccuracySec=30s
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF

sudo install -m 0644 "$SERVICE_FILE" "$SERVICE_PATH"
sudo install -m 0644 "$TIMER_FILE" "$TIMER_PATH"
sudo systemctl daemon-reload
sudo systemctl reset-failed "$SERVICE_NAME" >/dev/null 2>&1 || true
sudo systemctl enable --now "$TIMER_NAME"

echo
echo "Auto-update timer installed:"
sudo systemctl --no-pager --full status "$TIMER_NAME"
echo
echo "Manual check:"
echo "  sudo systemctl start $SERVICE_NAME"
echo
echo "Logs:"
echo "  journalctl -u $SERVICE_NAME -n 100 --no-pager"
echo
echo "Full diagnostic:"
echo "  sh $PROJECT_DIR/server-autoupdate-status.sh $BRANCH"
