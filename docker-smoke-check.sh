#!/usr/bin/env sh
set -eu

echo "== compose services =="
docker compose ps

echo "== api health =="
curl -fsS http://127.0.0.1:8000/ >/dev/null
echo "api: ok"

echo "== ffmpeg =="
docker compose exec -T api ffmpeg -version | head -n 1
docker compose exec -T api ffprobe -version | head -n 1

echo "== python deps =="
docker compose exec -T api python -c "import yt_dlp; import faster_whisper; print('yt-dlp/faster-whisper: ok')"
docker compose exec -T api python -c "import shutil; print('ffprobe:', shutil.which('ffprobe')); import importlib.util; print('PyAV:', 'ok' if importlib.util.find_spec('av') else 'missing, ffprobe fallback is used')"

echo "== bot logs =="
docker compose logs --tail=20 bot

echo "== api logs =="
docker compose logs --tail=20 api
