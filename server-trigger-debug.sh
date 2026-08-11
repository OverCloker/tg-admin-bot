#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CHAT_ID=${1:-}
if [ "$#" -gt 0 ]; then
    shift
fi
TRIGGER=${*:-}

cd "$PROJECT_DIR"

if [ -z "$CHAT_ID" ] || [ -z "$TRIGGER" ]; then
    echo "Usage: sh server-trigger-debug.sh <chat_id> <trigger>"
    echo "Example: sh server-trigger-debug.sh -1001234567890 клип"
    exit 2
fi

echo "== git =="
git -c safe.directory="$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || true
git -c safe.directory="$PROJECT_DIR" status --short --branch --untracked-files=no 2>/dev/null || true
echo

echo "== docker =="
docker compose ps bot api
echo

echo "== ffmpeg / ffprobe in api =="
docker compose exec -T api sh -lc 'command -v ffmpeg; ffmpeg -version | head -n 1; command -v ffprobe; ffprobe -version | head -n 1'
echo

echo "== python media imports in api =="
docker compose exec -T api python - <<'PY'
import shutil
print("ffprobe:", shutil.which("ffprobe"))
try:
    import av
    print("PyAV: ok", getattr(av, "__version__", "unknown"))
except Exception as exc:
    print("PyAV: missing", type(exc).__name__, str(exc))
PY
echo

echo "== trigger rows =="
docker compose exec -T api env DEBUG_CHAT_ID="$CHAT_ID" DEBUG_TRIGGER="$TRIGGER" python - <<'PY'
import os
from pathlib import Path
from app.config import load_config
from app.db import Database, normalize_trigger

chat_id = int(os.environ["DEBUG_CHAT_ID"])
trigger = normalize_trigger(os.environ["DEBUG_TRIGGER"])
db = Database(load_config().db_path)
try:
    db.init()
    print("DB:", load_config().db_path)
    print("chat_id:", chat_id)
    print("trigger:", trigger)
    base = next((item for item in db.list_triggers(chat_id) if item.trigger == trigger), None)
    print("base:", None if base is None else {
        "text": base.text,
        "media_type": base.media_type,
        "media_file_id_prefix": (base.media_file_id or "")[:32],
    })
    variants = db.list_trigger_variants(chat_id, trigger)
    if not variants:
        print("variants: none")
    for index, item in enumerate(variants, start=1):
        media_file_id = item.media_file_id or ""
        exists = None
        if media_file_id.startswith("local:"):
            exists = Path(media_file_id.removeprefix("local:")).exists()
        print(index, {
            "variant_type": item.variant_type,
            "text": item.text,
            "media_type": item.media_type,
            "media_file_id_prefix": media_file_id[:80],
            "local_exists": exists,
        })
    print("aliases:", db.list_trigger_aliases(chat_id, trigger))
finally:
    db.close()
PY
echo

echo "== recent trigger/media errors =="
docker compose logs --tail=300 bot api | grep -Ei 'trigger|триггер|media|video|document|ffprobe|ffmpeg|TelegramBadRequest' || true
