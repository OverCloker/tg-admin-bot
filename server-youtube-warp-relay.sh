#!/bin/sh
set -eu

# This script is installed root-owned outside the Git checkout. It discovers
# Docker's private addresses, then drops privileges before accepting traffic.
gateway=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
subnet=$(docker network inspect otveto4ka_default --format '{{(index .IPAM.Config 0).Subnet}}')

case "$gateway" in
    ''|*[!0-9.]*) echo "Invalid Docker gateway: $gateway" >&2; exit 1 ;;
esac
case "$subnet" in
    ''|*[!0-9./]*) echo "Invalid otveto4ka subnet: $subnet" >&2; exit 1 ;;
esac

if ! warp-cli --accept-tos settings | grep -q 'Mode: WarpProxy on port 40000'; then
    echo 'WARP must be configured as WarpProxy on port 40000.' >&2
    exit 1
fi
if ! warp-cli --accept-tos status | grep -q 'Status update: Connected'; then
    warp-cli --accept-tos connect >/dev/null
fi

exec setpriv --reuid=nobody --regid=nogroup --clear-groups \
    socat "TCP4-LISTEN:40001,bind=$gateway,reuseaddr,fork,range=$subnet" \
          'TCP4:127.0.0.1:40000'
