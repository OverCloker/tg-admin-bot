#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKUP_DIR=${1:-}
CONFIRM=${2:-}

if [ -z "$BACKUP_DIR" ] || [ "$CONFIRM" != "--yes" ]; then
    echo "Использование: sh server-restore.sh /путь/к/otveto4ka-ДАТА --yes"
    exit 1
fi

BACKUP_DIR=$(CDPATH= cd -- "$BACKUP_DIR" && pwd)
for file in volumes.tar.gz env.production SHA256SUMS; do
    if [ ! -f "$BACKUP_DIR/$file" ]; then
        echo "В архиве отсутствует $file"
        exit 1
    fi
done

(
    cd "$BACKUP_DIR"
    sha256sum -c SHA256SUMS
)

cd "$PROJECT_DIR"
restart_services() {
    docker compose up -d >/dev/null 2>&1 || true
}
trap restart_services EXIT INT TERM

docker compose stop bot api
docker compose run --rm --no-deps \
    --user 0:0 \
    --entrypoint sh \
    -v "$BACKUP_DIR:/backup:ro" \
    api \
    -c "tar -xzf /backup/volumes.tar.gz -C /"

cp "$BACKUP_DIR/env.production" "$PROJECT_DIR/.env"
chmod 0600 "$PROJECT_DIR/.env"

docker compose up -d
trap - EXIT INT TERM

echo "Данные восстановлены."
docker compose ps
