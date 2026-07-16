FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Kiev

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        gosu \
        libgomp1 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY README.md ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /app/downloads /app/logs /app/media_storage \
    && chown -R app:app /data /app /home/app \
    && chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENV DB_PATH=/data/bot.sqlite3 \
    ADMIN_ACCESS_KEYS_FILE=/data/admin_access_keys.json \
    FFMPEG_PATH=/usr/bin/ffmpeg

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

CMD ["python", "-m", "app.bot"]
