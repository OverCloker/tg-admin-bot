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
        libgomp1 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY README.md ./

RUN mkdir -p /data /app/downloads /app/logs /app/media_storage

ENV DB_PATH=/data/bot.sqlite3 \
    ADMIN_ACCESS_KEYS_FILE=/data/admin_access_keys.json \
    FFMPEG_PATH=/usr/bin/ffmpeg

EXPOSE 8000

CMD ["python", "-m", "app.bot"]
