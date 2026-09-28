#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo sh $0" >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v warp-cli >/dev/null 2>&1; then
    echo 'Install and register Cloudflare WARP first.' >&2
    exit 1
fi
if ! command -v socat >/dev/null 2>&1; then
    apt-get update
    apt-get install -y socat
fi

install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$project_dir/server-youtube-warp-relay.sh" \
    /usr/local/libexec/otveto4ka-youtube-warp-relay
install -o root -g root -m 0644 "$project_dir/server-youtube-warp-relay.service" \
    /etc/systemd/system/otveto4ka-youtube-warp-relay.service
systemctl daemon-reload
systemctl enable --now otveto4ka-youtube-warp-relay.service
systemctl --no-pager --full status otveto4ka-youtube-warp-relay.service
