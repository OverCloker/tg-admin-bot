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
sudo apt install -y docker.io docker-compose-plugin curl
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

Optional deploy notifications:

```env
DEPLOY_NOTIFY_CHAT_ID=-1001234567890
DEPLOY_NOTIFY_THREAD_ID=
```

If `DEPLOY_NOTIFY_CHAT_ID` is set, `server-deploy.sh` sends a message before the
Docker rebuild starts and another message after the bot/API are started again.
Set `DEPLOY_NOTIFY_THREAD_ID` only when the notification must go into a specific
Telegram forum topic.

Optional values if used:

```env
ALERTS_API_TOKEN=
AUDD_API_TOKEN=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

Optional local Telegram Bot API server for publishing videos larger than 50 MB:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash_from_my_telegram_org
BOT_API_URL=http://telegram-bot-api:8081
BOT_API_PORT_BIND=127.0.0.1
```

`BOT_API_URL` is used by the Docker `bot` and `api` containers. Keep
`BOT_API_PORT_BIND=127.0.0.1` if only the Docker services need the local Bot API.
For the Windows Media Publisher over Tailscale, set `BOT_API_PORT_BIND` to the
server Tailscale IP and put `http://TAILSCALE_IP:8081` into the desktop app's
`Bot API URL` field.

Build and start:

The Mini App admin panel displays the running API image's Git revision, build
time and API process start time. A normal `docker compose build` stamps these
automatically from HEAD/refs in the checkout. Only Git reference metadata is
allowed into the build context; Git config, objects and credentials stay excluded.
The read-only build mount does not persist Git metadata in the final image.
See [Docker build mounts](https://docs.docker.com/reference/dockerfile/#run---mounttypebind).
A subsequent `git pull` does not change the running image's displayed revision.
Archives without Git metadata display an unknown revision. This identifies the
API/Mini App image, not the health or version of a separately running bot process,
and does not claim that the revision is the latest one on GitHub.

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 bot
docker compose logs -f --tail=100 api
```

To build and start the optional local Telegram Bot API server too:

```bash
docker compose --profile local-bot-api up -d --build
```

The first build can take a long time because Docker compiles the official
`telegram-bot-api` binary. Compilation uses one job by default to reduce peak
memory usage on small servers. To increase it on a server with enough RAM, set
`CMAKE_BUILD_PARALLEL_LEVEL=2` before the compose command; Compose passes this
value into the Docker build. One job still requires enough free RAM and disk.
If SSH is unstable, run the build in the background:

```bash
nohup sh -c 'docker compose --profile local-bot-api up -d --build' > local-bot-api-build.log 2>&1 &
tail -f local-bot-api-build.log
```

Before switching the production bot token to the local server, stop all running
bot processes that use the same token, then deregister the token from Telegram's
cloud Bot API once:

```bash
docker compose stop bot api
curl -fsS "https://api.telegram.org/bot$BOT_TOKEN/logOut"
docker compose --profile local-bot-api up -d --build
```

After this switch, keep all project processes on the same local Bot API endpoint.
Running the same token against both `https://api.telegram.org` and a local server
can break update delivery.

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
sh server-deploy.sh main
```

`server-deploy.sh` pulls `origin/main`, rebuilds the Docker image and restarts the
`bot` and `api` containers. If `CLOUDFLARE_TUNNEL_TOKEN` is present in `.env`, it
also keeps the Cloudflare tunnel profile enabled.

If `.env` contains `DEPLOY_NOTIFY_CHAT_ID`, the script writes into that Telegram
chat before and after the update:

```text
🔄 Бот уходит на обновление
Пожалуйста, пару минут не пишите команды — я пересобираюсь и перезапускаюсь.

✅ Бот снова запущен
Обновление завершено, команды можно использовать.
```

## Automatic Git updates

Install the auto-update timer once on Debian:

```bash
cd ~/tg-admin-bot
git pull origin main
sh server-install-autoupdate.sh main
```

By default Debian checks GitHub every 5 minutes. If `origin/main` has a newer
fast-forward commit, the server runs:

```bash
sh server-deploy.sh main
```

That means it pulls the commit, rebuilds Docker and restarts the bot/API. If there
are local tracked changes on the server, the update is skipped so the server does
not overwrite manual edits.

Useful commands:

```bash
systemctl list-timers otveto4ka-auto-update.timer
sudo systemctl start otveto4ka-auto-update.service
journalctl -u otveto4ka-auto-update.service -n 100 --no-pager
sh server-autoupdate-status.sh main
sudo systemctl disable --now otveto4ka-auto-update.timer
```

If the server does not update by itself, run:

```bash
cd ~/tg-admin-bot
git pull origin main
sh server-install-autoupdate.sh main
sh server-autoupdate-status.sh main
sudo systemctl start otveto4ka-auto-update.service
journalctl -u otveto4ka-auto-update.service -n 150 --no-pager
```

The status script prints the current local commit, `origin/main`, timer state,
last service result and recent logs. Auto-update skips deployment when tracked
server files are locally modified or when the local branch cannot fast-forward.

To change the interval during installation:

```bash
AUTO_UPDATE_INTERVAL=1min sh server-install-autoupdate.sh main
```

## Preparing the server for a physical move

The Telegram polling bot itself needs only an outgoing internet connection. It does
not need a public IP or router port forwarding. The API used by Android apps and
the Mini App is a separate concern; see the remote access section below.

Install the project systemd unit once:

```bash
cd ~/tg-admin-bot
git pull origin main
sh server-install-autostart.sh
```

This enables Docker and creates `otveto4ka-compose.service`. On every Debian boot,
systemd runs `docker compose --profile cloudflare up -d`, so the optional Cloudflare
Tunnel starts together with the bot and API. Docker keeps all containers alive with
their existing `restart: unless-stopped` policies.

Verify all boot services before the move:

```bash
sudo systemctl is-enabled docker
sudo systemctl is-enabled tailscaled
sudo systemctl is-enabled ssh
sudo systemctl is-enabled otveto4ka-compose
docker compose ps
curl -f http://127.0.0.1:8000/
```

Create a full backup on another disk or USB drive:

```bash
cd ~/tg-admin-bot
sh server-backup.sh /mnt/usb/otveto4ka-backups
```

The script briefly stops `bot` and `api`, archives all four Docker volumes, copies
the production `.env`, writes SHA-256 checksums, and starts the services again.
The resulting directory must be stored securely because it contains bot tokens
and administrator keys.

Power off cleanly before disconnecting the server:

```bash
sudo poweroff
```

After connecting Ethernet and power at the new location, DHCP, Docker, Tailscale,
SSH, the bot, and the API should start without a graphical login.

## Restoring on a replacement Debian server

Clone the repository and place the backup directory on the new server. Build the
image once, then restore:

```bash
git clone https://github.com/OverCloker/tg-admin-bot.git
cd tg-admin-bot
cp /path/to/backup/env.production .env
docker compose build
sh server-restore.sh /path/to/backup --yes
sh server-install-autostart.sh
```

Do not run the old and new bot containers at the same time: Telegram polling
allows only one active instance for the same bot token.

## Remote management from another city

Tailscale is the preferred administration channel. It works through NAT and a
changing public IP, and no incoming router ports are required.

On Debian:

```bash
sudo systemctl enable --now tailscaled
sudo systemctl enable --now ssh
sudo tailscale set --ssh=true
tailscale ip -4
tailscale status
```

Install Tailscale on the remote Windows/Android device and sign in to the same
tailnet. Then connect from Windows Terminal:

```powershell
ssh abbadon@100.110.102.7
```

Use the current address printed by `tailscale ip -4` if it differs. Tailscale
normally preserves this address when the same Debian installation is moved.

Common remote commands:

```bash
cd ~/tg-admin-bot
docker compose ps
docker compose logs --tail=100 bot
docker compose logs --tail=100 api
docker compose restart bot
docker compose restart api
git pull origin main
docker compose up -d --build
```

Portainer is available through Tailscale at:

```text
https://TAILSCALE_IP:9443
```

Verify that its container has an automatic restart policy:

```bash
docker inspect portainer --format '{{.HostConfig.RestartPolicy.Name}}'
```

If it prints `no`, set the policy once:

```bash
docker update --restart=always portainer
```

Do not expose SSH or Portainer directly to the public internet. For the owner's
Android apps, an address such as `http://TAILSCALE_IP:50000` is safe while the
phone is connected to Tailscale because traffic is carried inside the encrypted
Tailscale tunnel.

## Cloudflare Tunnel for the public API

Use Cloudflare Tunnel for the API, admin web panel and Mini App. It creates an
outbound connection from the home server, so no white IP, port forwarding or
open `8000`/`50000` port is needed.

Requirements:

- a domain added to the same Cloudflare account;
- a Cloudflare Zero Trust tunnel token;
- a public hostname, for example `bot.example.com`.

In Cloudflare Zero Trust create a tunnel, choose the Docker connector, copy its
token, and add it to the server `.env` without quotes:

```env
CLOUDFLARE_TUNNEL_TOKEN=the_secret_token_from_cloudflare
ADMIN_PUBLIC_URL=https://bot.example.com/
MINI_APP_URL=https://bot.example.com/miniapp
```

In the tunnel's Public Hostnames section add:

```text
Hostname: bot.example.com
Service: http://api:8000
```

The `api` hostname is the Compose service name and is resolvable by the
Cloudflare container on the project network. Start the optional tunnel service:

```bash
cd ~/tg-admin-bot
docker compose --profile cloudflare up -d
docker compose ps
docker compose logs --tail=80 cloudflared
```

After changing `ADMIN_PUBLIC_URL` or `MINI_APP_URL`, restart both application
containers so their menu buttons use the new address:

```bash
docker compose up -d --build bot api
```

Check from another city or mobile internet:

```text
https://bot.example.com/
https://bot.example.com/miniapp
```

Cloudflare Tunnel is for browser/API traffic. Keep SSH and Portainer behind
Tailscale. This gives the correct split: Cloudflare for users and Mini App,
Tailscale for private server administration.
