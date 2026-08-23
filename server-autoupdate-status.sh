#!/bin/sh
set -u

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BRANCH=${1:-main}
SERVICE_NAME=otveto4ka-auto-update.service
TIMER_NAME=otveto4ka-auto-update.timer
OLD_LOCK_DIR="${TMPDIR:-/tmp}/otveto4ka-auto-update.lock"
FALLBACK_LOCK_DIR="${TMPDIR:-/tmp}/otveto4ka-auto-update.lock.d"

cd "$PROJECT_DIR" || exit 1

echo "== project =="
echo "Dir: $PROJECT_DIR"
echo "User: $(id -un 2>/dev/null || echo unknown)"
echo

echo "== git =="
if command -v git >/dev/null 2>&1; then
    git -c safe.directory="$PROJECT_DIR" status --short --branch --untracked-files=no || true
    echo "Origin: $(git -c safe.directory="$PROJECT_DIR" remote get-url origin 2>/dev/null || echo missing)"
    echo "Local:  $(git -c safe.directory="$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
    if git -c safe.directory="$PROJECT_DIR" fetch origin "$BRANCH" >/dev/null 2>&1; then
        echo "Remote: $(git -c safe.directory="$PROJECT_DIR" rev-parse "origin/$BRANCH" 2>/dev/null || echo unknown)"
    else
        echo "Remote: fetch failed"
    fi
else
    echo "git not found"
fi
echo

echo "== update lock =="
if [ -d "$OLD_LOCK_DIR" ]; then
    echo "Legacy stale lock found: $OLD_LOCK_DIR"
    echo "It was created by an older updater and can be removed safely when no deploy is running."
elif [ -d "$FALLBACK_LOCK_DIR" ]; then
    echo "Fallback lock active: $FALLBACK_LOCK_DIR (PID $(cat "$FALLBACK_LOCK_DIR/pid" 2>/dev/null || echo unknown))"
else
    echo "No stale directory lock found."
fi
echo

echo "== systemd timer =="
if command -v systemctl >/dev/null 2>&1; then
    systemctl --no-pager --full status "$TIMER_NAME" || true
    echo
    systemctl list-timers --all "$TIMER_NAME" || true
else
    echo "systemctl not found"
fi
echo

echo "== last service run =="
if command -v systemctl >/dev/null 2>&1; then
    systemctl --no-pager --full status "$SERVICE_NAME" || true
fi
echo

echo "== recent logs =="
if command -v journalctl >/dev/null 2>&1; then
    journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true
else
    echo "journalctl not found"
fi
echo

echo "== manual commands =="
echo "Install/reinstall timer:"
echo "  sh $PROJECT_DIR/server-install-autoupdate.sh $BRANCH"
echo
echo "Run one update check now:"
echo "  sudo systemctl start $SERVICE_NAME"
echo
echo "Follow logs:"
echo "  journalctl -u $SERVICE_NAME -f"
