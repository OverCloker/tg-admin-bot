#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BRANCH=${1:-main}
LOCK_DIR="${TMPDIR:-/tmp}/otveto4ka-auto-update.lock"

cd "$PROJECT_DIR"

echo "== otveto4ka auto-update =="
echo "Time: $(date -Is 2>/dev/null || date)"
echo "Project: $PROJECT_DIR"
echo "Branch: $BRANCH"
echo "User: $(id -un 2>/dev/null || echo unknown)"

if ! command -v git >/dev/null 2>&1; then
    echo "git not found"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found"
    exit 1
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Another auto-update is already running."
    exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT INT TERM

git_safe() {
    git -c safe.directory="$PROJECT_DIR" "$@"
}

echo "Origin: $(git_safe remote get-url origin 2>/dev/null || echo missing)"
echo "Current branch: $(git_safe branch --show-current 2>/dev/null || echo unknown)"

if [ -n "$(git_safe status --porcelain --untracked-files=no)" ]; then
    echo "Tracked working tree files are not clean; auto-update skipped."
    git_safe status --short --untracked-files=no
    exit 1
fi

echo "== checking origin/$BRANCH =="
git_safe fetch origin "$BRANCH"

LOCAL_COMMIT=$(git_safe rev-parse HEAD)
REMOTE_COMMIT=$(git_safe rev-parse "origin/$BRANCH")

echo "Local:  $LOCAL_COMMIT"
echo "Remote: $REMOTE_COMMIT"

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo "Already up to date."
    exit 0
fi

if ! git_safe merge-base --is-ancestor "$LOCAL_COMMIT" "$REMOTE_COMMIT"; then
    echo "Local branch is not a fast-forward of origin/$BRANCH; auto-update skipped."
    exit 1
fi

echo "Update found:"
echo "Local:  $LOCAL_COMMIT"
echo "Remote: $REMOTE_COMMIT"
echo

exec sh "$PROJECT_DIR/server-deploy.sh" "$BRANCH"
