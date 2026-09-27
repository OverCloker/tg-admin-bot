#!/bin/sh
set -eu

for directory in /data /app/downloads /app/logs /app/media_storage; do
    marker="$directory/.owner-10001"
    if [ ! -e "$marker" ]; then
        chown -R app:app "$directory"
        gosu app touch "$marker"
    fi
done

exec gosu app "$@"
