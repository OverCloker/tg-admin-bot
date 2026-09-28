#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVICE_NAME=otveto4ka-telegram-backup.service
TIMER_NAME=otveto4ka-telegram-backup.timer

if ! command -v systemctl >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    echo "systemd and python3 are required"
    exit 1
fi

# Validate first: do not create an active timer with missing keys or recipients.
sudo python3 "$PROJECT_DIR/server-telegram-backup.py" --check

SERVICE_FILE=$(mktemp)
TIMER_FILE=$(mktemp)
trap 'rm -f "$SERVICE_FILE" "$TIMER_FILE"' EXIT

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Send encrypted OtvetO4ka SQLite backup to owner's Telegram chat
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/server-telegram-backup.py
SyslogIdentifier=otveto4ka-telegram-backup
UMask=0077
TimeoutStartSec=10min
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Daily encrypted OtvetO4ka backup

[Timer]
OnCalendar=*-*-* 03:15:00 UTC
RandomizedDelaySec=15min
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF

sudo install -m 0644 "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME"
sudo install -m 0644 "$TIMER_FILE" "/etc/systemd/system/$TIMER_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER_NAME"

echo "Backup timer installed. Verify a manual delivery with:"
echo "  sudo systemctl start $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -n 30 --no-pager"
echo "  sudo systemctl list-timers --all $TIMER_NAME"
