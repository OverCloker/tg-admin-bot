#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CHAT_ID=${1:-}
TEXT=${2:-}

cd "$PROJECT_DIR"

if [ -z "$CHAT_ID" ] || [ -z "$TEXT" ]; then
    echo "Usage: sh server-blacklist-debug.sh <chat_id> <text>"
    echo "Example: sh server-blacklist-debug.sh -1002461073129 'Вась'"
    exit 2
fi

echo "== git =="
git -c safe.directory="$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || true
git -c safe.directory="$PROJECT_DIR" status --short --branch --untracked-files=no 2>/dev/null || true
echo

echo "== docker =="
docker compose ps bot api
echo

echo "== blacklist match =="
docker compose exec -T api env DEBUG_CHAT_ID="$CHAT_ID" DEBUG_TEXT="$TEXT" python - <<'PY'
import os

from app.config import load_config
from app.db import Database
from app.bot import has_normalized_trigger, normalize_blacklist_text

chat_id = int(os.environ["DEBUG_CHAT_ID"])
original = os.environ["DEBUG_TEXT"]
text = normalize_blacklist_text(original)
config = load_config()
db = Database(config.db_path)
try:
    print("DB:", config.db_path)
    print("chat_id:", chat_id)
    print("input:", original)
    print("normalized:", text)
    print()

    print("chats:")
    for chat in db.list_chats():
        print(f"  {chat.chat_id} | {chat.title}")
    print()

    rules = db.list_blacklist_rules(chat_id)
    print("rules:", len(rules))
    matched = False
    for rule in rules:
        words = (rule.word, *tuple(rule.variants or ()))
        hits = [
            word
            for word in words
            if has_normalized_trigger(text, normalize_blacklist_text(word))
        ]
        if hits:
            matched = True
        print({
            "word": rule.word,
            "variants": list(rule.variants or ()),
            "hits": hits,
        })
    print()
    print("MATCH:", matched)
finally:
    db.close()
PY

