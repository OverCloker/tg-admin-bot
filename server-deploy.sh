#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BRANCH=${1:-}
GIT_SAFE_DIR="$PROJECT_DIR"
DEPLOY_NOTICE_STARTED=0
DEPLOY_NOTICE_DONE=0

cd "$PROJECT_DIR"

env_value() {
    key=$1
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        return 0
    fi
    sed -n "s/^${key}=//p" "$PROJECT_DIR/.env" | tail -n 1 | sed "s/^['\"]//; s/['\"]$//"
}

send_deploy_notice() {
    text=$1
    token=$(env_value BOT_TOKEN)
    chat_id=$(env_value DEPLOY_NOTIFY_CHAT_ID)
    thread_id=$(env_value DEPLOY_NOTIFY_THREAD_ID)

    if [ -z "$token" ] || [ -z "$chat_id" ]; then
        return 0
    fi
    if ! command -v curl >/dev/null 2>&1; then
        echo "curl not found; deploy Telegram notice skipped"
        return 0
    fi

    if [ -n "$thread_id" ]; then
        curl --silent --show-error --fail --max-time 15 --request POST \
            --data-urlencode "chat_id=$chat_id" \
            --data-urlencode "message_thread_id=$thread_id" \
            --data-urlencode "parse_mode=HTML" \
            --data-urlencode "disable_web_page_preview=true" \
            --data-urlencode "text=$text" \
            "https://api.telegram.org/bot$token/sendMessage" >/dev/null || true
    else
        curl --silent --show-error --fail --max-time 15 --request POST \
            --data-urlencode "chat_id=$chat_id" \
            --data-urlencode "parse_mode=HTML" \
            --data-urlencode "disable_web_page_preview=true" \
            --data-urlencode "text=$text" \
            "https://api.telegram.org/bot$token/sendMessage" >/dev/null || true
    fi
}

deploy_exit_notice() {
    status=$?
    if [ "$DEPLOY_NOTICE_STARTED" = "1" ] && [ "$DEPLOY_NOTICE_DONE" = "0" ]; then
        send_deploy_notice "$(printf "⚠️ <b>Обновление не завершилось</b>\nКоманды уже можно пробовать осторожно, но лучше проверить серверные логи.")"
    fi
    exit "$status"
}

trap deploy_exit_notice EXIT

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

if [ -n "$(git -c safe.directory="$GIT_SAFE_DIR" status --porcelain --untracked-files=no)" ]; then
    echo "Tracked working tree files are not clean. Commit/stash local server changes first."
    git -c safe.directory="$GIT_SAFE_DIR" status --short --untracked-files=no
    exit 1
fi

if [ -z "$BRANCH" ]; then
    BRANCH=$(git -c safe.directory="$GIT_SAFE_DIR" branch --show-current)
fi
if [ -z "$BRANCH" ]; then
    echo "Cannot detect current git branch. Pass it explicitly: sh server-deploy.sh main"
    exit 1
fi

echo "== git =="
git -c safe.directory="$GIT_SAFE_DIR" fetch origin "$BRANCH"
git -c safe.directory="$GIT_SAFE_DIR" pull --ff-only origin "$BRANCH"

DEPLOY_NOTICE_STARTED=1
send_deploy_notice "$(printf "🔄 <b>Бот уходит на обновление</b>\nПожалуйста, пару минут не пишите команды — я пересобираюсь и перезапускаюсь.")"

COMPOSE_PROFILE_ARGS=""
if grep -Eq '^CLOUDFLARE_TUNNEL_TOKEN=.' "$PROJECT_DIR/.env"; then
    COMPOSE_PROFILE_ARGS="--profile cloudflare"
fi

echo "== docker compose config =="
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILE_ARGS config --quiet

echo "== docker compose build =="
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILE_ARGS build --pull bot api

echo "== docker compose up =="
if [ -n "$COMPOSE_PROFILE_ARGS" ]; then
    # shellcheck disable=SC2086
    docker compose $COMPOSE_PROFILE_ARGS up -d --remove-orphans
else
    docker compose up -d --remove-orphans bot api
fi

echo "== status =="
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILE_ARGS ps

echo "== recent logs =="
# shellcheck disable=SC2086
docker compose $COMPOSE_PROFILE_ARGS logs --tail=80 bot api

DEPLOY_NOTICE_DONE=1
send_deploy_notice "$(printf "✅ <b>Бот снова запущен</b>\nОбновление завершено, команды можно использовать.")"

echo
echo "Deploy done."
