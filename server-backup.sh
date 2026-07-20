#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKUP_ROOT=${1:-"$PROJECT_DIR/backups"}
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/otveto4ka-$STAMP"

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Не найден $PROJECT_DIR/.env"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
cd "$PROJECT_DIR"

restart_services() {
    docker compose up -d >/dev/null 2>&1 || true
}
trap restart_services EXIT INT TERM

echo "Останавливаю bot и api для целостной копии SQLite..."
docker compose stop bot api

docker compose run --rm --no-deps \
    --user 0:0 \
    --entrypoint sh \
    -v "$BACKUP_DIR:/backup" \
    api \
    -c "tar -czf /backup/volumes.tar.gz /data /app/downloads /app/logs /app/media_storage"

cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env.production"
cp "$PROJECT_DIR/docker-compose.yml" "$BACKUP_DIR/docker-compose.yml"
chmod 0600 "$BACKUP_DIR/env.production"

(
    cd "$BACKUP_DIR"
    sha256sum volumes.tar.gz env.production docker-compose.yml >SHA256SUMS
)

docker compose up -d
trap - EXIT INT TERM

echo
echo "Резервная копия готова: $BACKUP_DIR"
du -sh "$BACKUP_DIR"
echo "Проверка:"
echo "  cd '$BACKUP_DIR' && sha256sum -c SHA256SUMS"
