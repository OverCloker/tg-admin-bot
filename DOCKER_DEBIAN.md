# Debian Docker deployment

This file describes the production Docker layout for the Telegram bot, FastAPI server, media processing, and the two Android apps.

## What runs in Docker

- `bot` service: Telegram polling bot.
- `api` service: FastAPI server with admin panel, user app API, Premium, media tasks, analytics, weather, YouTube worker.
- One shared SQLite database in Docker volume `bot_data`.
- Shared persistent media volumes:
  - `bot_downloads` -> `/app/downloads`
  - `bot_media` -> `/app/media_storage`
  - `bot_logs` -> `/app/logs`

The API listens inside the container on port `8000`. Docker publishes both:

```text
8000:8000
50000:8000
```

That keeps old Android app settings working if they use either `:8000` or `:50000`.

## Debian prerequisites

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

Optional but recommended:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

## First deploy

Copy the whole `telegram_autoreply_bot` directory to the Debian server.

Create `.env` from `.env.example`:

```bash
cp .env.example .env
nano .env
```

Required values:

```env
BOT_TOKEN=real_token_from_botfather
BOT_ADMIN_IDS=123456789
OWNER_ID=123456789
ADMIN_API_KEY=long_random_admin_key
ADMIN_ACTOR_ID=123456789
DB_PATH=/data/bot.sqlite3
ADMIN_ACCESS_KEYS_FILE=/data/admin_access_keys.json
ADMIN_PUBLIC_URL=http://SERVER_IP:8000/
FFMPEG_PATH=/usr/bin/ffmpeg
WHISPER_MODEL=small
```

Optional values if used:

```env
ALERTS_API_TOKEN=
AUDD_API_TOKEN=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

Build and start:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 bot
docker compose logs -f --tail=100 api
```

Short smoke check:

```bash
sh docker-smoke-check.sh
```

## Migrating current data

Stop the Windows bot/API before copying the database, so SQLite WAL data is flushed.

Recommended on Windows before copy:

```powershell
cd C:\Users\Иго\Documents\Codex\2026-05-27\new-chat\telegram_autoreply_bot
.\stop-all.cmd
```

Copy these files/directories to Debian:

```text
bot.sqlite3
admin_access_keys.json
downloads/
media_storage/
logs/
.env
```

Then import them into Docker volumes:

```bash
docker compose down
docker compose up -d --build
docker compose stop bot api

docker run --rm -v telegram_autoreply_bot_bot_data:/data -v "$PWD":/backup busybox sh -c 'cp /backup/bot.sqlite3 /data/bot.sqlite3 && [ -f /backup/admin_access_keys.json ] && cp /backup/admin_access_keys.json /data/admin_access_keys.json || true'
docker run --rm -v telegram_autoreply_bot_bot_downloads:/target -v "$PWD/downloads":/source busybox sh -c 'cp -a /source/. /target/ 2>/dev/null || true'
docker run --rm -v telegram_autoreply_bot_bot_media:/target -v "$PWD/media_storage":/source busybox sh -c 'cp -a /source/. /target/ 2>/dev/null || true'
docker run --rm -v telegram_autoreply_bot_bot_logs:/target -v "$PWD/logs":/source busybox sh -c 'cp -a /source/. /target/ 2>/dev/null || true'

docker compose up -d
```

If the project directory name differs, check exact volume names:

```bash
docker volume ls | grep bot
```

## Android apps after migration

Both Android apps stay outside Docker.

- MonkeyDin: set server address to `http://SERVER_IP:8000` or `http://SERVER_IP:50000`.
- Abstergo Control: set panel address to `http://SERVER_IP:8000/` or `http://SERVER_IP:50000/`.

If Debian has a firewall:

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 50000/tcp
```

## Runtime checks

```bash
docker compose ps
curl -f http://127.0.0.1:8000/
docker compose logs --tail=100 bot
docker compose logs --tail=100 api
```

Inside the API container:

```bash
docker compose exec api ffmpeg -version
docker compose exec api python -c "import yt_dlp; print('yt-dlp ok')"
docker compose exec api python -c "import faster_whisper; print('faster-whisper ok')"
```

## Backup

```bash
mkdir -p backups
docker compose stop bot api
docker run --rm -v telegram_autoreply_bot_bot_data:/data -v "$PWD/backups":/backup busybox sh -c 'cp /data/bot.sqlite3 /backup/bot.sqlite3.$(date +%Y%m%d-%H%M%S)'
docker compose up -d
```

## Update

```bash
docker compose down
docker compose up -d --build
docker compose logs -f --tail=100
```
