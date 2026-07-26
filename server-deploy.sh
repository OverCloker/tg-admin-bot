#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BRANCH=${1:-}

cd "$PROJECT_DIR"

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

if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is not clean. Commit/stash local server changes first."
    git status --short
    exit 1
fi

if [ -z "$BRANCH" ]; then
    BRANCH=$(git branch --show-current)
fi
if [ -z "$BRANCH" ]; then
    echo "Cannot detect current git branch. Pass it explicitly: sh server-deploy.sh main"
    exit 1
fi

echo "== git =="
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

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

echo
echo "Deploy done."
