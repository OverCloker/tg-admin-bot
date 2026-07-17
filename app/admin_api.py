import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import ipaddress
import socket
import subprocess
import sys
import tempfile
import time
import aiohttp
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from urllib.parse import quote, urlparse
from typing import Annotated, Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, LabeledPrice
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .config import load_config
from .db import Database, normalize_trigger, normalize_username, utc_now
from .media_tasks import MediaTaskService, SUPPORTED_TASK_TYPES
from .media_processor import find_ffmpeg
from .premium import PLANS, PREMIUM_PERIOD_DAYS, PremiumError, PremiumLimitError, PremiumRequiredError, PremiumService, plan_public_dict
from .staff import StaffService
from .user_profile import build_user_profile
from .youtube_media import DOWNLOAD_TYPES, YoutubeMediaError, cleanup_youtube_file, download_youtube, inspect_youtube
from .miniapp import router as miniapp_router


app = FastAPI(title="Telegram Autoreply Bot Admin API")
app.include_router(miniapp_router)
YOUTUBE_WORKER_TASK: asyncio.Task | None = None

CURRENT_ADMIN_ACTOR_ID: ContextVar[int | None] = ContextVar("current_admin_actor_id", default=None)
CURRENT_ADMIN_CHAT_ID: ContextVar[int | None] = ContextVar("current_admin_chat_id", default=None)
SESSION_TOKENS: dict[str, dict[str, Any]] = {}
ADMIN_MEMBERSHIP_CACHE: dict[tuple[int, int], tuple[float, bool]] = {}
ADMIN_MEMBERSHIP_CACHE_SECONDS = 45
ACCESS_KEY_PREFIX = "tbp_"
ACCESS_SESSION_HOURS = 24 * 7
USER_SESSION_PREFIX = "usr_"
USER_LOGIN_TTL_MINUTES = 10
USER_SESSION_DAYS = 180
USER_SUBSCRIPTION_PERIOD = 30 * 24 * 60 * 60
ADMIN_FEATURES: list[dict[str, str]] = [
    {"id": "addReply", "title": "Добавить @ответ"},
    {"id": "deleteReply", "title": "Удалить @ответ"},
    {"id": "triggers", "title": "Список триггеров"},
    {"id": "participants", "title": "Топ участников"},
    {"id": "checkAccess", "title": "Проверить доступ"},
    {"id": "giveaway", "title": "Настроить розыгрыш"},
    {"id": "restart", "title": "Перезагрузка"},
    {"id": "alarm", "title": "Режим тревоги"},
    {"id": "rollMute", "title": "Roll mute"},
    {"id": "quiet", "title": "Затихни"},
    {"id": "blacklist", "title": "Черный список слов"},
    {"id": "quotes", "title": "Цитаты"},
    {"id": "send", "title": "Написать в чат"},
    {"id": "feedback", "title": "Обратная связь"},
    {"id": "ads", "title": "Реклама"},
    {"id": "stars", "title": "Звезды"},
    {"id": "premium", "title": "Premium"},
    {"id": "analytics", "title": "Аналитика"},
    {"id": "mine", "title": "Шахта"},
    {"id": "logs", "title": "Логи"},
]
ADMIN_FEATURE_IDS = {item["id"] for item in ADMIN_FEATURES}
ADMIN_SUBFEATURES: dict[str, list[dict[str, str]]] = {
    "triggers": [
        {"id": "triggers.add", "title": "Добавить слово"},
        {"id": "triggers.delete", "title": "Удалить слово"},
    ],
    "blacklist": [
        {"id": "blacklist.add", "title": "Добавить слово"},
        {"id": "blacklist.delete", "title": "Удалить слово"},
    ],
    "quotes": [
        {"id": "quotes.add", "title": "Добавить цитату"},
        {"id": "quotes.delete", "title": "Удалить цитату"},
    ],
    "send": [
        {"id": "send.text", "title": "Отправить текст"},
        {"id": "send.media", "title": "Отправить медиа"},
        {"id": "send.voice", "title": "Отправить голосовое"},
    ],
    "giveaway": [
        {"id": "giveaway.settings", "title": "Настройки розыгрыша"},
        {"id": "giveaway.birthdays", "title": "Дни рождения"},
    ],
    "alarm": [
        {"id": "alarm.toggle", "title": "Включить/выключить"},
        {"id": "alarm.text", "title": "Тексты тревоги"},
    ],
    "rollMute": [
        {"id": "rollMute.settings", "title": "Настройки строк"},
    ],
    "quiet": [
        {"id": "quiet.manual", "title": "Замутить"},
        {"id": "quiet.text", "title": "Текст ответа"},
        {"id": "quiet.mediaSave", "title": "Сохранить медиа"},
        {"id": "quiet.mediaDelete", "title": "Удалить медиа"},
    ],
    "mine": [
        {"id": "mine.grant", "title": "Начислить/забрать ресурсы"},
    ],
    "feedback": [
        {"id": "feedback.send", "title": "Отправить сообщение"},
    ],
    "ads": [
        {"id": "ads.add", "title": "Добавить рекламу"},
        {"id": "ads.edit", "title": "Редактировать рекламу"},
        {"id": "ads.delete", "title": "Удалить рекламу"},
        {"id": "ads.settings", "title": "Настройки рекламы"},
    ],
}
ADMIN_PERMISSION_IDS = ADMIN_FEATURE_IDS | {item["id"] for items in ADMIN_SUBFEATURES.values() for item in items}


async def notify_staff_autoreply_change(description: str) -> None:
    config = load_config()
    staff = StaffService(config.db_path, config.owner_id)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await staff.auto_reply_changed(bot, description)
    except Exception:
        logging.exception("Could not notify Staff System about an autoreply change")
    finally:
        await bot.session.close()
        staff.close()


async def notify_staff_api_audit(actor_name: str, action: str, chat_title: str | None, details: str) -> None:
    config = load_config()
    staff = StaffService(config.db_path, config.owner_id)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    lines = [
        f"<b>{escape(action)}</b>",
        f"Кто: {escape(actor_name)}",
    ]
    if chat_title:
        lines.append(f"Группа: {escape(chat_title)}")
    lines.append(f"Действие: <code>{escape(details)}</code>")
    try:
        await staff.send(bot, "logs", "\n".join(lines))
    except Exception:
        logging.exception("Could not notify Staff System about an API audit action")
    finally:
        await bot.session.close()
        staff.close()


async def notify_staff_critical(text: str) -> None:
    config = load_config()
    staff = StaffService(config.db_path, config.owner_id)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await staff.log(bot, "CRITICAL", text, notify=True)
    finally:
        await bot.session.close()
        staff.close()


async def youtube_queue_worker() -> None:
    next_cleanup_at = 0.0
    while True:
        media = MediaTaskService(load_config().db_path)
        task = None
        output_path = None
        try:
            now = asyncio.get_running_loop().time()
            if now >= next_cleanup_at:
                next_cleanup_at = now + 60 * 60
                removed = media.cleanup_stale_files(max_age_hours=24)
                if removed:
                    media.premium.log("INFO", f"Expired media files removed: {removed}")
            task = media.claim_next_youtube_task()
            if task is None:
                await asyncio.sleep(3)
                continue
            download_type = task.source_file_id or ""
            if download_type not in DOWNLOAD_TYPES or not task.source_file_path:
                raise YoutubeMediaError("YouTube-задача содержит некорректные параметры.")
            plan = media.premium.get_user_plan(task.user_id)
            if plan is None:
                raise PremiumRequiredError("Для этой функции нужен Premium.")
            output_path = await asyncio.to_thread(
                download_youtube,
                task.source_file_path,
                download_type,
                task.id,
                plan.max_file_size_bytes,
            )
            actual_size = os.path.getsize(output_path)
            if actual_size > plan.max_file_size_bytes:
                cleanup_youtube_file(output_path)
                output_path = None
                raise PremiumLimitError(
                    f"Итоговый файл превышает лимит тарифа: {plan.max_file_size_bytes // (1024 * 1024)} МБ."
                )
            media.set_output_file_path(task.id, output_path)
            media.update_media_task_status(task.id, "completed")
            media.premium.log("INFO", f"YouTube API task completed: id={task.id}, bytes={actual_size}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if task is not None:
                media.update_media_task_status(task.id, "failed", str(exc))
                media.premium.log("ERROR", f"YouTube API task failed: id={task.id}, error={exc}")
            logging.exception("YouTube queue worker failed")
            if not isinstance(exc, (YoutubeMediaError, PremiumRequiredError, PremiumLimitError)):
                await notify_staff_critical(f"Критическая ошибка YouTube-worker: {exc!r}")
            await asyncio.sleep(2)
        finally:
            media.close()


@app.on_event("startup")
async def start_youtube_worker() -> None:
    global YOUTUBE_WORKER_TASK
    if YOUTUBE_WORKER_TASK is None or YOUTUBE_WORKER_TASK.done():
        YOUTUBE_WORKER_TASK = asyncio.create_task(youtube_queue_worker())


@app.on_event("shutdown")
async def stop_youtube_worker() -> None:
    global YOUTUBE_WORKER_TASK
    if YOUTUBE_WORKER_TASK is not None:
        YOUTUBE_WORKER_TASK.cancel()
        with suppress(asyncio.CancelledError):
            await YOUTUBE_WORKER_TASK
        YOUTUBE_WORKER_TASK = None


ADMIN_PANEL_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель бота</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --card: #ffffff;
      --control: #ffffff;
      --menu-bg: #eef2f6;
      --menu-text: #172033;
      --button-bg: #176b87;
      --button-text: #ffffff;
      --secondary-bg: #eef2f6;
      --secondary-text: #172033;
      --field-bg: #ffffff;
      --field-text: #172033;
      --field-muted: #667085;
      --file-button-bg: #eef2f6;
      --file-button-text: #172033;
      --text: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --primary: #176b87;
      --primary-soft: #e7f3f7;
      --danger: #b42318;
      --danger-text: #ffffff;
      --bg-scrim-color: 246, 248, 251;
      --bg-scrim: 1;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      background-image: var(--bg-image, none);
      background-size: cover;
      background-position: center;
      background-attachment: fixed;
      color: var(--text);
      font-family: Arial, system-ui, sans-serif;
      overscroll-behavior: none;
    }
    body.modal-locked {
      overflow: hidden;
      position: fixed;
      left: 0;
      right: 0;
      width: 100%;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background: rgba(var(--bg-scrim-color), var(--bg-scrim, 1));
    }
    body > * { position: relative; z-index: 1; }
    header {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--card);
      border-bottom: 1px solid var(--line);
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .icon-button {
      width: 44px;
      height: 44px;
      padding: 0;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      line-height: 1;
      flex: 0 0 auto;
    }
    h1 { margin: 0; font-size: 22px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 16px;
      display: grid;
      gap: 14px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
      overflow-wrap: break-word;
    }
    #status, #weatherStatus, #actionBody, .muted, .title, .text {
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    body.theme-dark {
      --bg: #111827;
      --card: #1f2937;
      --control: #ffffff;
      --menu-bg: #4b5563;
      --menu-text: #ffffff;
      --button-bg: #6b7280;
      --button-text: #ffffff;
      --secondary-bg: #4b5563;
      --secondary-text: #ffffff;
      --field-bg: #4b5563;
      --field-text: #ffffff;
      --field-muted: #cbd5e1;
      --file-button-bg: #6b7280;
      --file-button-text: #ffffff;
      --text: #f9fafb;
      --muted: #cbd5e1;
      --line: #374151;
      --primary: #9ca3af;
      --primary-soft: #6b7280;
      --danger: #7f1d1d;
      --danger-text: #ffffff;
      --bg-scrim-color: 17, 24, 39;
      --bg-scrim: 0.82;
    }
    body.theme-green {
      --bg: #f3faf6;
      --card: #ffffff;
      --control: #ffffff;
      --menu-bg: #eaf5ee;
      --menu-text: #14231b;
      --button-bg: #247a4d;
      --button-text: #ffffff;
      --secondary-bg: #e2f3e9;
      --secondary-text: #14231b;
      --field-bg: #eaf5ee;
      --field-text: #14231b;
      --field-muted: #60736a;
      --file-button-bg: #e2f3e9;
      --file-button-text: #14231b;
      --text: #14231b;
      --muted: #60736a;
      --line: #d7e7dd;
      --primary: #247a4d;
      --primary-soft: #e2f3e9;
      --bg-scrim-color: 243, 250, 246;
      --bg-scrim: 0.86;
    }
    body.theme-oled {
      --bg: #000000;
      --card: #050505;
      --control: #0f0f0f;
      --menu-bg: #111111;
      --menu-text: #f7f7f7;
      --button-bg: #1f2937;
      --button-text: #ffffff;
      --secondary-bg: #141414;
      --secondary-text: #ffffff;
      --field-bg: #0d0d0d;
      --field-text: #ffffff;
      --field-muted: #a3a3a3;
      --file-button-bg: #141414;
      --file-button-text: #ffffff;
      --text: #ffffff;
      --muted: #b8b8b8;
      --line: #262626;
      --primary: #60a5fa;
      --primary-soft: #111827;
      --danger: #7f1d1d;
      --danger-text: #ffffff;
      --bg-scrim-color: 0, 0, 0;
      --bg-scrim: 0.94;
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .action-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 18px;
    }
    .action-header h2 {
      padding-top: 8px;
    }
    .action-body {
      display: grid;
      gap: 14px;
    }
    .admin-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    input, textarea {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      font: inherit;
      background: var(--field-bg);
      color: var(--field-text);
    }
    input::placeholder, textarea::placeholder { color: var(--field-muted); }
    input[type="checkbox"] { width: auto; }
    input[type="file"] {
      padding: 10px;
      color: var(--field-text);
    }
    input[type="file"]::file-selector-button {
      margin-right: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--file-button-bg);
      color: var(--file-button-text);
      font: inherit;
    }
    input[type="file"]::-webkit-file-upload-button {
      margin-right: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--file-button-bg);
      color: var(--file-button-text);
      font: inherit;
    }
    textarea { min-height: 96px; resize: vertical; }
    button {
      border: 0;
      border-radius: 8px;
      padding: 11px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      background: var(--button-bg);
      color: var(--button-text);
    }
    button.secondary { background: var(--secondary-bg); color: var(--secondary-text); }
    button.danger { background: var(--danger); color: var(--danger-text); }
    button.menu {
      min-height: 58px;
      text-align: left;
      background: var(--menu-bg);
      color: var(--menu-text);
      touch-action: pan-y;
      user-select: none;
      -webkit-user-select: none;
      -webkit-touch-callout: none;
      font-size: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
    }
    button.menu {
      grid-column: span 2;
    }
    button.menu.small {
      grid-column: span 1;
      min-height: 58px;
      padding: 11px 14px;
      font-size: 16px;
      text-align: center;
    }
    button.menu.normal {
      grid-column: span 2;
      min-height: 58px;
    }
    button.menu.large {
      grid-column: 1 / -1;
      min-height: 58px;
      font-size: 16px;
    }
    button.menu.drag-picked {
      outline: 3px solid var(--primary);
      outline-offset: 2px;
    }
    button.menu.drag-over {
      box-shadow: inset 0 0 0 3px var(--primary);
    }
    button.menu:hover, button.secondary:hover { background: var(--primary-soft); color: var(--menu-text); }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 5;
      background: rgba(16, 24, 40, 0.42);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      overscroll-behavior: contain;
      touch-action: none;
    }
    .modal {
      width: min(460px, 100%);
      background: var(--card);
      border-radius: 8px;
      border: 1px solid var(--line);
      padding: 16px;
      box-shadow: 0 18px 44px rgba(16, 24, 40, 0.22);
      display: grid;
      gap: 12px;
    }
    .settings-modal {
      width: min(720px, 100%);
      max-height: calc(100vh - 32px);
      overflow: auto;
      overscroll-behavior: contain;
      touch-action: pan-y;
      -webkit-overflow-scrolling: touch;
    }
    .settings-block {
      display: grid;
      gap: 10px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    .settings-block:first-child {
      padding-top: 0;
      border-top: 0;
    }
    .app-settings-form {
      display: grid;
      gap: 14px;
    }
    .form-stack {
      display: grid;
      gap: 14px;
    }
    .modal label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 14px;
    }
    select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      font: inherit;
      background: var(--field-bg);
      color: var(--field-text);
    }
    .muted { color: var(--muted); }
    .hidden { display: none; }
    .chat {
      width: 100%;
      text-align: left;
      background: var(--menu-bg);
      color: var(--menu-text);
      border: 1px solid var(--line);
    }
    .chat.active { background: var(--menu-bg); color: var(--menu-text); border-color: var(--primary); }
    .chat .muted { color: currentColor; opacity: 0.72; }
    .item {
      border-top: 1px solid var(--line);
      padding: 10px 0;
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }
    .item > div { flex: 1; min-width: 0; }
    .title { font-weight: 700; overflow-wrap: anywhere; }
    .text { color: var(--muted); overflow-wrap: anywhere; white-space: pre-wrap; }
    #toast {
      position: fixed;
      left: 50%;
      bottom: 18px;
      transform: translateX(-50%);
      background: #101828;
      color: #fff;
      padding: 10px 14px;
      border-radius: 8px;
      max-width: calc(100vw - 32px);
    }
    @media (max-width: 720px) {
      .grid { grid-template-columns: 1fr; }
      .admin-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      header { align-items: center; flex-direction: row; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Abstergo Control</h1>
      <div class="muted">Панель управления OtvetO4ka</div>
    </div>
    <div class="row">
      <button class="icon-button secondary" onclick="openRadio()" aria-label="radio">&#128251;</button>
      <button class="icon-button secondary" onclick="openSettings()" aria-label="settings">&#9881;</button>
    </div>
  </header>
  <main>
    <section class="card hidden" id="legacyConnectionCard">
      <h2>Подключение</h2>
      <div class="row">
        <input id="apiKey" type="password" placeholder="Ключ доступа">
        <button onclick="saveKey()">Сохранить</button>
        <button class="secondary" onclick="loadAll()">Обновить</button>
      </div>
    </section>

    <section class="card" id="statusCard">
      <h2>Статус</h2>
      <div id="status" class="muted">Введите ключ и нажмите «Обновить».</div>
    </section>

    <section class="card hidden" id="weatherCard">
      <h2>Погода</h2>
      <div id="weatherStatus" class="muted">Настрой город в параметрах приложения.</div>
    </section>

    <section class="card hidden" id="globalPremiumCard">
      <h2>Premium</h2>
      <div class="muted">Покупатели, тарифы и сроки подписок.</div>
      <button style="margin-top:12px" onclick="showAction('premium', 'Premium')">Открыть Premium</button>
    </section>

    <section class="card">
      <h2>Выбор группы</h2>
      <div id="chats" class="grid"></div>
    </section>

    <section class="card hidden" id="adminCard">
      <h2 id="chatTitle">Настройки группы</h2>
      <div class="row" style="margin-bottom:10px">
        <span class="muted" id="buttonModeHint"></span>
      </div>
      <div id="adminMenu" class="grid admin-grid"></div>
    </section>

    <section class="card hidden" id="actionCard">
      <div class="action-header">
        <h2 id="actionTitle">Действие</h2>
        <button class="secondary" onclick="showMenu()">Назад</button>
      </div>
      <div id="actionBody" class="action-body"></div>
    </section>
  </main>
  <div id="toast" class="hidden"></div>
  <div id="buttonModal" class="modal-backdrop hidden">
    <div class="modal">
      <h2 id="buttonModalTitle">Настройка кнопки</h2>
      <label>
        <span><input id="buttonUseColor" type="checkbox"> Свой цвет</span>
        <input id="buttonColor" type="color" value="#eef2f6">
      </label>
      <label>
        Ширина
        <select id="buttonSize">
          <option value="small">Маленькая - половина</option>
          <option value="normal">Обычная - одна кнопка</option>
          <option value="large">Большая - вся строка</option>
        </select>
      </label>
      <div class="row">
        <button class="secondary" onclick="moveButton(-1)">Выше</button>
        <button class="secondary" onclick="moveButton(1)">Ниже</button>
      </div>
      <div class="row">
        <button onclick="saveButtonAppearance()">Сохранить</button>
        <button class="secondary" onclick="resetButtonAppearance()">Сбросить</button>
        <button class="secondary" onclick="closeButtonSettings()">Закрыть</button>
      </div>
    </div>
  </div>

  <div id="settingsModal" class="modal-backdrop hidden" onclick="closeSettings()">
    <div class="modal settings-modal" onclick="event.stopPropagation()">
      <div class="row" style="justify-content: space-between">
        <h2>Настройки</h2>
        <button class="secondary" onclick="closeSettings()">Закрыть</button>
      </div>
      <div class="settings-block">
        <h2>Подключение</h2>
        <div class="row">
          <input id="settingsApiKey" type="password" placeholder="Ключ доступа">
          <button onclick="saveKey()">Сохранить</button>
          <button class="secondary" onclick="loadAll()">Обновить</button>
        </div>
      </div>
      <div class="settings-block">
        <h2>Кнопки панели</h2>
        <div class="row">
          <button class="secondary" id="settingsReorderToggle" onclick="toggleReorderMode()">Перемещение</button>
          <button class="secondary" id="settingsEditToggle" onclick="toggleEditMode()">Размер / цвет</button>
          <button class="secondary" onclick="resetAllButtonSettings()">Сбросить кнопки</button>
        </div>
        <div class="muted" id="settingsButtonHint">Выбери режим, затем работай с кнопками в панели группы.</div>
      </div>
      <div class="settings-block hidden" id="accessKeysBlock">
        <h2>Ключи доступа</h2>
        <div id="accessKeysBody"></div>
      </div>
      <div class="settings-block">
        <h2>Настройки приложения</h2>
        <div id="settingsAppBody"></div>
      </div>
    </div>
  </div>

  <div id="radioModal" class="modal-backdrop hidden" onclick="closeRadio()">
    <div class="modal settings-modal" onclick="event.stopPropagation()">
      <div class="row" style="justify-content: space-between">
        <h2>Radio Browser</h2>
        <button class="secondary" onclick="closeRadio()">Закрыть</button>
      </div>
      <div class="form-stack">
        <div class="row">
          <input id="radioSearch" placeholder="Название станции или жанр">
          <button onclick="searchRadioStations()">Найти</button>
          <button class="secondary" onclick="showFavoriteRadioStations()">Избранное</button>
        </div>
        <div id="radioNow" class="muted">Станция не выбрана.</div>
        <audio id="radioPlayer" controls style="width:100%"></audio>
        <div id="radioStations" class="form-stack"></div>
      </div>
    </div>
  </div>

  <script>
    let selectedChatId = null;
    let overview = null;
    let stars = [];
    let premiumSubscriptions = { items: [], total: 0 };
    let digTop = { depth: [], coins: [] };
    let digPlayers = { items: [], total: 0, page: 1, perPage: 20 };
    let analyticsData = { summary: null, items: [] };
    let radioResults = [];
    let analyticsAppOpenSent = false;
    let ownerActionsAllowed = false;
    let ownerOnlyActionsAllowed = false;
    let adminPermissions = {};
    let adminFeaturePermissions = {};
    let editingButtonId = null;
    let longPressTimer = null;
    let longPressFired = false;
    let longPressStartX = 0;
    let longPressStartY = 0;
    let reorderMode = false;
    let editMode = false;
    let pickedButtonId = null;
    let draggedButtonId = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let nativeVoiceBase64 = null;
    let nativeVoiceMime = "audio/mp4";
    let nativeVoiceFilename = "voice.m4a";
    let lockedScrollY = 0;
    let weatherTimer = null;

    const defaultActions = [
      { id: "addReply", title: "Добавить @ответ" },
      { id: "deleteReply", title: "Удалить @ответ" },
      { id: "triggers", title: "Список триггеров" },
      { id: "participants", title: "Топ участников" },
      { id: "checkAccess", title: "Проверить доступ" },
      { id: "giveaway", title: "Настроить розыгрыш" },
      { id: "restart", title: "Перезагрузка" },
      { id: "alarm", title: "Режим тревоги" },
      { id: "rollMute", title: "Roll mute" },
      { id: "quiet", title: "Затихни" },
      { id: "blacklist", title: "Черный список слов" },
      { id: "quotes", title: "Цитаты" },
      { id: "send", title: "Написать в чат" },
      { id: "feedback", title: "Обратная связь" },
      { id: "ads", title: "Реклама" },
      { id: "stars", title: "Звезды" },
      { id: "premium", title: "Premium" },
      { id: "analytics", title: "Аналитика" },
      { id: "mine", title: "Шахта" },
      { id: "logs", title: "Логи" },
      { id: "access", title: "Доступ" },
      { id: "appSettings", title: "Настройки приложения" },
    ];
    let buttonSettings = loadButtonSettings();

    function key() {
      const field = document.getElementById("settingsApiKey") || document.getElementById("apiKey");
      return localStorage.getItem("adminSessionToken")
        || (field ? field.value.trim() : "")
        || localStorage.getItem("adminApiKey")
        || "";
    }

    function headers() {
      return {
        "Authorization": "Bearer " + key(),
        "Content-Type": "application/json"
      };
    }

    function toast(text) {
      const el = document.getElementById("toast");
      el.textContent = text;
      el.classList.remove("hidden");
      setTimeout(() => el.classList.add("hidden"), 2400);
    }

    function adminDeviceInfo() {
      if (window.AndroidApp && window.AndroidApp.getDeviceInfo) {
        try {
          return JSON.parse(window.AndroidApp.getDeviceInfo());
        } catch (_) {}
      }
      return {
        appVersion: "web-panel",
        androidVersion: navigator.userAgent,
        model: navigator.platform || "",
        screen: `${window.screen.width}x${window.screen.height}`,
        density: String(window.devicePixelRatio || 1),
        locale: navigator.language || "",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
        networkType: navigator.connection ? (navigator.connection.effectiveType || navigator.connection.type || "") : ""
      };
    }

    function reportAdminAnalytics(eventName, eventType = "event", extra = {}) {
      if (!key() || eventName === "api:/admin/analytics") return;
      const payload = {
        app: "Abstergo",
        eventType,
        eventName,
        device: adminDeviceInfo(),
        ...extra
      };
      fetch("/admin/analytics", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(payload)
      }).catch(() => {});
    }

    async function api(path, options = {}) {
      const started = performance.now();
      try {
        let response = await fetch(path, {
          ...options,
          headers: { ...headers(), ...(options.headers || {}) }
        });
        const durationMs = Math.round(performance.now() - started);
        if (!path.startsWith("/admin/analytics")) {
          reportAdminAnalytics(`api:${path}`, response.ok ? "api" : "error", {
            endpoint: path,
            statusCode: response.status,
            durationMs,
            errorType: response.ok ? null : "http"
          });
        }
        if (!response.ok) {
          let detail = await response.text();
          try {
            const parsed = JSON.parse(detail);
            detail = parsed.detail || detail;
          } catch (_) {}
          throw new Error(`${response.status}: ${detail}`);
        }
        return response.json();
      } catch (error) {
        if (!path.startsWith("/admin/analytics")) {
          reportAdminAnalytics(`api:${path}`, "error", {
            endpoint: path,
            durationMs: Math.round(performance.now() - started),
            errorType: error.name || "network",
            message: String(error.message || error).slice(0, 240)
          });
        }
        throw error;
      }
    }

    async function saveKey() {
      const field = document.getElementById("settingsApiKey") || document.getElementById("apiKey");
      const accessKey = field ? field.value.trim() : "";
      if (!accessKey) {
        toast("Введи ключ доступа");
        return;
      }
      const response = await fetch("/admin/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessKey })
      });
      if (!response.ok) {
        localStorage.removeItem("adminSessionToken");
        toast("Ключ не принят этим сервером");
        return;
      }
      const session = await response.json();
      localStorage.setItem("adminSessionToken", session.sessionToken);
      // Keep the original key locally so a server restart can create a new session.
      // It never leaves this WebView except in the login request.
      localStorage.setItem("adminApiKey", accessKey);
      if (field) field.value = "";
      syncKeyFields();
      toast("Вход выполнен");
      loadAll();
    }

    async function loginWithStoredKey() {
      const accessKey = (localStorage.getItem("adminApiKey") || "").trim();
      if (!accessKey) return false;
      try {
        const response = await fetch("/admin/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accessKey })
        });
        if (!response.ok) {
          localStorage.removeItem("adminSessionToken");
          return false;
        }
        const session = await response.json();
        localStorage.setItem("adminSessionToken", session.sessionToken);
        return true;
      } catch (_) {
        return false;
      }
    }

    function syncKeyFields() {
      const legacy = document.getElementById("apiKey");
      const settings = document.getElementById("settingsApiKey");
      if (legacy) legacy.value = "";
      if (settings) settings.value = "";
    }

    function canView(feature) {
      if (ownerActionsAllowed) return true;
      const item = adminFeaturePermissions && adminFeaturePermissions[feature];
      if (item && typeof item === "object") return Boolean(item.view);
      return Boolean(adminPermissions && adminPermissions[feature]);
    }

    function canWrite(feature) {
      if (ownerActionsAllowed) return true;
      const item = adminFeaturePermissions && adminFeaturePermissions[feature];
      if (item && typeof item === "object") return Boolean(item.write);
      return Boolean(adminPermissions && adminPermissions[feature]);
    }

    function canUse(feature) {
      return canView(feature);
    }

    function writeLocked(feature) {
      return !canWrite(feature) ? `<p class="muted">Есть доступ к просмотру, но изменение этой кнопки закрыто.</p>` : "";
    }

    function openSettings() {
      syncKeyFields();
      document.getElementById("settingsAppBody").innerHTML = appSettingsForm();
      renderAccessKeysBlock();
      updateReorderHint();
      lockPageScroll();
      document.getElementById("settingsModal").classList.remove("hidden");
    }

    function closeSettings() {
      document.getElementById("settingsModal").classList.add("hidden");
      unlockPageScroll();
    }

    function openRadio() {
      lockPageScroll();
      document.getElementById("radioModal").classList.remove("hidden");
      const last = loadLastRadioStation();
      if (last) {
        const player = document.getElementById("radioPlayer");
        player.src = last.url;
        document.getElementById("radioNow").textContent = `Последняя станция: ${last.name}`;
      }
      if (!document.getElementById("radioStations").children.length) searchRadioStations();
    }

    function closeRadio() {
      document.getElementById("radioModal").classList.add("hidden");
      unlockPageScroll();
    }

    function handleAndroidBack() {
      const buttonModal = document.getElementById("buttonModal");
      const settingsModal = document.getElementById("settingsModal");
      const radioModal = document.getElementById("radioModal");
      const actionCard = document.getElementById("actionCard");
      const adminCard = document.getElementById("adminCard");
      if (buttonModal && !buttonModal.classList.contains("hidden")) {
        closeButtonSettings();
        return true;
      }
      if (settingsModal && !settingsModal.classList.contains("hidden")) {
        closeSettings();
        return true;
      }
      if (radioModal && !radioModal.classList.contains("hidden")) {
        closeRadio();
        return true;
      }
      if (actionCard && !actionCard.classList.contains("hidden")) {
        showMenu();
        return true;
      }
      if (adminCard && !adminCard.classList.contains("hidden")) {
        adminCard.classList.add("hidden");
        selectedChatId = null;
        overview = null;
        loadAll();
        return true;
      }
      return false;
    }
    window.handleAndroidBack = handleAndroidBack;

    async function searchRadioStations() {
      const query = document.getElementById("radioSearch").value.trim();
      const target = document.getElementById("radioStations");
      target.innerHTML = `<div class="muted">Ищу станции...</div>`;
      const params = new URLSearchParams({
        hidebroken: "true",
        codec: "MP3",
        order: "clickcount",
        reverse: "true",
        limit: "30",
      });
      if (query) params.set("name", query);
      try {
        const response = await fetch(`https://de1.api.radio-browser.info/json/stations/search?${params}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        radioResults = await response.json();
        target.innerHTML = radioResults.map((station, index) => `
          <div class="row">
            <button class="secondary" style="flex:1" onclick="playRadioStation(${index})">
              ${escapeHtml(station.name || "Без названия")}
            </button>
            <button class="secondary" onclick="toggleFavoriteRadioStation(${index})">
              ${isFavoriteRadioStation(station.stationuuid) ? "★" : "☆"}
            </button>
          </div>
        `).join("") || `<div class="muted">Станции не найдены.</div>`;
      } catch (error) {
        target.innerHTML = `<div class="muted">Не удалось загрузить станции: ${escapeHtml(error.message)}</div>`;
      }
    }

    function playRadioStation(index) {
      const station = radioResults[index];
      const player = document.getElementById("radioPlayer");
      player.src = station.url_resolved || station.url;
      player.play();
      document.getElementById("radioNow").textContent = `Сейчас играет: ${station.name}`;
      localStorage.setItem("lastRadioStation", JSON.stringify({
        name: station.name || "Без названия",
        url: station.url_resolved || station.url,
        uuid: station.stationuuid || "",
      }));
      fetch(`https://de1.api.radio-browser.info/json/url/${station.stationuuid || station.uuid}`).catch(() => {});
    }

    function loadLastRadioStation() {
      try {
        return JSON.parse(localStorage.getItem("lastRadioStation") || "null");
      } catch (_) {
        return null;
      }
    }

    function loadFavoriteRadioStations() {
      try {
        return JSON.parse(localStorage.getItem("favoriteRadioStations") || "[]");
      } catch (_) {
        return [];
      }
    }

    function isFavoriteRadioStation(uuid) {
      return loadFavoriteRadioStations().some(station => station.uuid === uuid);
    }

    function toggleFavoriteRadioStation(index) {
      const station = radioResults[index];
      const favorites = loadFavoriteRadioStations();
      const existing = favorites.findIndex(item => item.uuid === station.stationuuid);
      if (existing >= 0) favorites.splice(existing, 1);
      else favorites.push({
        name: station.name || "Без названия",
        url: station.url_resolved || station.url,
        uuid: station.stationuuid || "",
      });
      localStorage.setItem("favoriteRadioStations", JSON.stringify(favorites));
      renderRadioResults();
    }

    function showFavoriteRadioStations() {
      radioResults = loadFavoriteRadioStations().map(station => ({
        name: station.name,
        url: station.url,
        url_resolved: station.url,
        stationuuid: station.uuid,
      }));
      renderRadioResults();
    }

    function renderRadioResults() {
      const target = document.getElementById("radioStations");
      target.innerHTML = radioResults.map((station, index) => `
        <div class="row">
          <button class="secondary" style="flex:1" onclick="playRadioStation(${index})">
            ${escapeHtml(station.name || "Без названия")}
          </button>
          <button class="secondary" onclick="toggleFavoriteRadioStation(${index})">
            ${isFavoriteRadioStation(station.stationuuid) ? "★" : "☆"}
          </button>
        </div>
      `).join("") || `<div class="muted">В избранном пока нет станций.</div>`;
    }

    function lockPageScroll() {
      if (document.body.classList.contains("modal-locked")) return;
      lockedScrollY = window.scrollY || document.documentElement.scrollTop || 0;
      document.body.style.top = `-${lockedScrollY}px`;
      document.body.classList.add("modal-locked");
    }

    function unlockPageScroll() {
      if (!document.body.classList.contains("modal-locked")) return;
      document.body.classList.remove("modal-locked");
      document.body.style.top = "";
      window.scrollTo(0, lockedScrollY);
    }

    async function renderAccessKeysBlock() {
      const block = document.getElementById("accessKeysBlock");
      const body = document.getElementById("accessKeysBody");
      if (!block || !body) return;
      block.classList.toggle("hidden", !ownerActionsAllowed);
      if (!ownerActionsAllowed) return;
      body.innerHTML = `
        <div class="form-stack">
          <input id="accessKeyLabel" placeholder="Название ключа">
          <input id="accessKeyUserId" placeholder="Telegram user ID">
          <button onclick="createAccessKey()">Выдать ключ</button>
          <button class="danger" onclick="deleteInactiveAccessKeys()">Удалить неактивные</button>
        </div>
        <div id="newAccessKeyBox"></div>
        <div id="accessKeyList" class="form-stack" style="margin-top:14px"></div>
      `;
      await loadAccessKeys();
    }

    async function loadAccessKeys() {
      if (!ownerActionsAllowed) return;
      const items = await api("/admin/access-keys");
      const box = document.getElementById("accessKeyList");
      if (!box) return;
      box.innerHTML = items.length
        ? items.map(item => `
          <div class="item">
            <div>
              <div class="title">${escapeHtml(item.label)} · ${item.userId}</div>
              <div class="text">${item.revokedAt ? "отозван" : "активен"} · ${item.createdAt || ""}</div>
            </div>
            ${item.revokedAt ? "" : `<button class="danger" onclick="revokeAccessKey('${item.id}')">Отозвать</button>`}
          </div>
        `).join("")
        : `<p class="muted">Ключей пока нет.</p>`;
    }

    async function createAccessKey() {
      const label = val("accessKeyLabel");
      const userId = Number(val("accessKeyUserId"));
      const item = await api("/admin/access-keys", {
        method: "POST",
        body: JSON.stringify({ label, userId })
      });
      document.getElementById("newAccessKeyBox").innerHTML = `
        <div class="item">
          <div>
            <div class="title">Новый ключ</div>
            <div class="text">${escapeHtml(item.accessKey)}</div>
          </div>
        </div>
      `;
      await loadAccessKeys();
    }

    async function revokeAccessKey(id) {
      await api(`/admin/access-keys/${id}`, { method: "DELETE" });
      await loadAccessKeys();
      toast("Ключ отозван");
    }

    async function deleteInactiveAccessKeys() {
      if (!confirm("Удалить все отозванные ключи?")) return;
      const result = await api("/admin/access-keys/inactive", { method: "DELETE" });
      await loadAccessKeys();
      toast(`Удалено ключей: ${result.deleted || 0}`);
    }

    async function loadPermissions() {
      if (!ownerActionsAllowed) return;
      const adminsBox = document.getElementById("permissionAdmins");
      const target = document.getElementById("permissionFeatures");
      if (!adminsBox || !target) return;
      if (!selectedChatId) {
        adminsBox.innerHTML = `<p class="muted">Сначала выбери группу.</p>`;
        target.innerHTML = "";
        return;
      }
      const data = await api(`/admin/permissions?chatId=${selectedChatId}`);
      const admins = await api(`/admin/chats/${selectedChatId}/admins`);
      const permissions = data.permissions || [];
      const byUser = {};
      permissions.forEach(item => {
        byUser[item.user_id] = byUser[item.user_id] || {};
        byUser[item.user_id][item.feature] = Boolean(item.allowed);
      });
      const activeUser = Number(target.dataset.userId || 0);
      adminsBox.innerHTML = (admins.admins || []).length
        ? (admins.admins || []).map(admin => `
          <button class="secondary ${admin.userId === activeUser ? "active" : ""}" onclick="selectPermissionUser(${admin.userId})">
            ${escapeHtml(admin.fullName || admin.username || String(admin.userId))}
          </button>
        `).join("")
        : `<p class="muted">Не удалось получить админов группы.</p>`;
      const renderForUser = (userId) => {
        const current = byUser[userId] || {};
        if (!userId) {
          target.innerHTML = `<p class="muted">Выбери админа группы.</p>`;
          return;
        }
        target.innerHTML = (data.features || []).map(feature => {
          const children = (data.subFeatures && data.subFeatures[feature.id]) || [];
          const childRows = children.map(child => `
            <div class="item" style="margin-left:16px">
              <span>${escapeHtml(child.title)}</span>
              <div class="row">
                <label><input type="checkbox" ${permissionValue(current, child.id, "view") ? "checked" : ""} onchange="setPermission(${userId}, '${child.id}', 'view', this.checked)"> Читать</label>
                <label><input type="checkbox" ${permissionValue(current, child.id, "write") ? "checked" : ""} onchange="setPermission(${userId}, '${child.id}', 'write', this.checked)"> Нажимать</label>
              </div>
            </div>
          `).join("");
          return `
          <div class="item">
            <span>${escapeHtml(feature.title)}</span>
            <div class="row">
              <label><input type="checkbox" ${permissionValue(current, feature.id, "view") ? "checked" : ""} onchange="setPermission(${userId}, '${feature.id}', 'view', this.checked)"> Читать</label>
              <label><input type="checkbox" ${permissionValue(current, feature.id, "write") ? "checked" : ""} onchange="setPermission(${userId}, '${feature.id}', 'write', this.checked)"> Изменять</label>
            </div>
          </div>
          ${children.length ? `<details><summary>Подпункты</summary><div class="form-stack" style="margin-top:10px">${childRows}</div></details>` : ""}
        `;
        }).join("");
      };
      renderForUser(activeUser);
    }

    function permissionValue(current, feature, mode) {
      const modeKey = `${feature}.${mode}`;
      if (Object.prototype.hasOwnProperty.call(current, modeKey)) return Boolean(current[modeKey]);
      if (Object.prototype.hasOwnProperty.call(current, feature)) return Boolean(current[feature]);
      if (feature.includes(".")) {
        const parent = feature.split(".")[0];
        const parentModeKey = `${parent}.${mode}`;
        if (Object.prototype.hasOwnProperty.call(current, parentModeKey)) return Boolean(current[parentModeKey]);
        if (Object.prototype.hasOwnProperty.call(current, parent)) return Boolean(current[parent]);
      }
      return false;
    }

    async function selectPermissionUser(userId) {
      const target = document.getElementById("permissionFeatures");
      if (target) target.dataset.userId = String(userId);
      await loadPermissions();
    }

    async function setPermission(userId, feature, mode, allowed) {
      userId = Number(userId);
      if (!userId) {
        toast("Выбери админа группы");
        await loadPermissions();
        return;
      }
      await api("/admin/permissions", {
        method: "POST",
        body: JSON.stringify({ chatId: selectedChatId, userId, feature, mode, allowed })
      });
      toast("Доступ обновлен");
      await loadPermissions();
    }

    async function loadAll() {
      try {
        if (!analyticsAppOpenSent) {
          analyticsAppOpenSent = true;
          reportAdminAnalytics("app_open");
        }
        const status = await api("/admin/status");
        ownerActionsAllowed = Boolean(status.ownerActionsAllowed);
        ownerOnlyActionsAllowed = Boolean(status.ownerOnlyActionsAllowed);
        adminPermissions = status.permissions || {};
        adminFeaturePermissions = status.featurePermissions || {};
        document.getElementById("status").textContent =
          `${status.name} @${status.username} · вход: ${status.currentUserId || "неизвестен"}${status.ownerActionsAllowed ? " (владелец, полный доступ)" : ""} · групп: ${status.chats} · участников: ${status.participants} · Stars: ${status.starAmount} · шахта: ${status.digPlayers}`;
        document.getElementById("globalPremiumCard").classList.toggle("hidden", !ownerActionsAllowed);

        const chats = await api("/admin/chats");
        renderChats(chats);
        stars = canUse("stars") ? await api("/admin/stars/payments") : [];
        premiumSubscriptions = ownerActionsAllowed ? await api("/admin/premium/subscriptions") : { items: [], total: 0 };
        analyticsData = ownerActionsAllowed ? await api("/admin/analytics?limit=80") : { summary: null, items: [] };
        digTop = canUse("mine") ? await api("/admin/dig/top") : { depth: [], coins: [] };
        digPlayers = canUse("mine") ? await api("/admin/dig/players?page=1&per_page=20") : { items: [], total: 0, page: 1, perPage: 20 };
        await refreshWeather();
        scheduleWeatherRefresh();
      } catch (error) {
        toast(error.message || "Ошибка подключения");
        console.error(error);
      }
    }

    function renderChats(chats) {
      const box = document.getElementById("chats");
      box.innerHTML = "";
      chats.forEach(chat => {
        const button = document.createElement("button");
        button.className = "chat" + (chat.chat_id === selectedChatId ? " active" : "");
        button.innerHTML = `<div class="title">${escapeHtml(chat.title)}</div>`;
        button.onclick = () => selectChat(chat.chat_id);
        box.appendChild(button);
      });
    }

    async function selectChat(chatId) {
      selectedChatId = chatId;
      overview = await api(`/admin/chats/${chatId}/overview`);
      adminPermissions = overview.permissions || adminPermissions || {};
      adminFeaturePermissions = overview.featurePermissions || adminFeaturePermissions || {};
      document.getElementById("chatTitle").textContent = overview.chat.title;
      document.getElementById("adminCard").classList.remove("hidden");
      showMenu();
    }

    function showMenu() {
      document.getElementById("actionCard").classList.add("hidden");
      if (!overview) {
        document.getElementById("adminCard").classList.add("hidden");
        return;
      }
      document.getElementById("adminCard").classList.remove("hidden");
      const menu = document.getElementById("adminMenu");
      menu.innerHTML = "";
      updateReorderHint();
      orderedActions().forEach(({ id, title }) => {
        const button = document.createElement("button");
        const style = buttonSettings.styles[id] || {};
        button.className = `menu ${normalizedButtonSize(style.size)}`;
        if (reorderMode && pickedButtonId === id) button.classList.add("drag-picked");
        button.textContent = title;
        button.draggable = true;
        if (style.color) {
          button.style.backgroundColor = style.color;
          button.style.color = textColorFor(style.color);
        }
        button.onpointerdown = (event) => startButtonHold(event, id, title);
        button.onpointermove = moveButtonHold;
        button.onpointerup = cancelButtonHold;
        button.onpointercancel = cancelButtonHold;
        button.onpointerleave = cancelButtonHold;
        button.onclick = (event) => {
          if (longPressFired) {
            event.preventDefault();
            longPressFired = false;
            return;
          }
          if (reorderMode) {
            event.preventDefault();
            pickOrPlaceButton(id);
            return;
          }
          if (editMode) {
            event.preventDefault();
            openButtonSettings(id, title);
            return;
          }
          showAction(id, title);
        };
        button.ondragstart = (event) => {
          draggedButtonId = id;
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", id);
        };
        button.ondragover = (event) => {
          event.preventDefault();
          button.classList.add("drag-over");
        };
        button.ondragleave = () => button.classList.remove("drag-over");
        button.ondrop = (event) => {
          event.preventDefault();
          button.classList.remove("drag-over");
          moveButtonBefore(draggedButtonId || event.dataTransfer.getData("text/plain"), id);
          draggedButtonId = null;
        };
        menu.appendChild(button);
      });
    }

    function loadButtonSettings() {
      const fallback = { order: defaultActions.map(item => item.id), styles: {} };
      try {
        const parsed = JSON.parse(localStorage.getItem("adminButtonSettings") || "{}");
        return {
          order: Array.isArray(parsed.order) ? parsed.order : fallback.order,
          styles: parsed.styles && typeof parsed.styles === "object" ? parsed.styles : {}
        };
      } catch (_) {
        return fallback;
      }
    }

    function saveButtonSettings() {
      localStorage.setItem("adminButtonSettings", JSON.stringify(buttonSettings));
    }

    function orderedActions() {
      const byId = Object.fromEntries(defaultActions.map(item => [item.id, item]));
      const ids = [...new Set([...(buttonSettings.order || []), ...defaultActions.map(item => item.id)])]
        .filter(id => byId[id] && id !== "appSettings")
        .filter(id => id === "access" ? ownerActionsAllowed : canUse(id));
      buttonSettings.order = ids;
      return ids.map(id => byId[id]);
    }

    function startButtonHold(event, id, title) {
      longPressFired = false;
      longPressStartX = event.clientX;
      longPressStartY = event.clientY;
      clearTimeout(longPressTimer);
      longPressTimer = setTimeout(() => {
        longPressFired = true;
        openButtonSettings(id, title);
      }, 1500);
    }

    function moveButtonHold(event) {
      if (Math.hypot(event.clientX - longPressStartX, event.clientY - longPressStartY) > 10) {
        cancelButtonHold();
      }
    }

    function cancelButtonHold() {
      clearTimeout(longPressTimer);
    }

    function openButtonSettings(id, title) {
      editingButtonId = id;
      const style = buttonSettings.styles[id] || {};
      document.getElementById("buttonModalTitle").textContent = `Настройка: ${title}`;
      document.getElementById("buttonColor").value = style.color || "#eef2f6";
      document.getElementById("buttonUseColor").checked = Boolean(style.color);
      document.getElementById("buttonSize").value = normalizedButtonSize(style.size);
      document.getElementById("buttonModal").classList.remove("hidden");
    }

    function closeButtonSettings() {
      editingButtonId = null;
      document.getElementById("buttonModal").classList.add("hidden");
    }

    function saveButtonAppearance() {
      if (!editingButtonId) return;
      const next = { size: document.getElementById("buttonSize").value };
      if (document.getElementById("buttonUseColor").checked) {
        next.color = document.getElementById("buttonColor").value;
      }
      buttonSettings.styles[editingButtonId] = next;
      saveButtonSettings();
      showMenu();
      closeButtonSettings();
      toast("Кнопка настроена");
    }

    function resetButtonAppearance() {
      if (!editingButtonId) return;
      delete buttonSettings.styles[editingButtonId];
      saveButtonSettings();
      showMenu();
      closeButtonSettings();
      toast("Настройка сброшена");
    }

    function moveButton(direction) {
      if (!editingButtonId) return;
      const order = orderedActions().map(item => item.id);
      const index = order.indexOf(editingButtonId);
      const next = index + direction;
      if (index < 0 || next < 0 || next >= order.length) return;
      [order[index], order[next]] = [order[next], order[index]];
      buttonSettings.order = order;
      saveButtonSettings();
      showMenu();
      const item = defaultActions.find(action => action.id === editingButtonId);
      if (item) openButtonSettings(item.id, item.title);
    }

    function toggleReorderMode() {
      if (!selectedChatId) {
        toast("Сначала выбери группу");
        return;
      }
      reorderMode = !reorderMode;
      if (reorderMode) editMode = false;
      pickedButtonId = null;
      closeSettings();
      showMenu();
    }

    function toggleEditMode() {
      if (!selectedChatId) {
        toast("Сначала выбери группу");
        return;
      }
      editMode = !editMode;
      if (editMode) {
        reorderMode = false;
        pickedButtonId = null;
      }
      closeSettings();
      showMenu();
    }

    function resetAllButtonSettings() {
      buttonSettings = {
        order: defaultActions.map(item => item.id).filter(id => id !== "appSettings"),
        styles: {}
      };
      saveButtonSettings();
      reorderMode = false;
      editMode = false;
      pickedButtonId = null;
      if (selectedChatId) showMenu();
      updateReorderHint();
      toast("Кнопки сброшены");
    }

    function updateReorderHint() {
      const reorderButton = document.getElementById("settingsReorderToggle");
      const editButton = document.getElementById("settingsEditToggle");
      const panelHint = document.getElementById("buttonModeHint");
      const settingsHint = document.getElementById("settingsButtonHint");
      if (reorderButton) reorderButton.textContent = reorderMode ? "Готово" : "Перемещение";
      if (editButton) editButton.textContent = editMode ? "Готово" : "Размер / цвет";
      const text = reorderMode
        ? "Нажми кнопку, затем место для вставки. На ПК можно перетаскивать."
        : editMode
          ? "Нажми любую кнопку ниже, чтобы изменить размер или цвет."
          : "";
      if (panelHint) panelHint.textContent = text;
      if (settingsHint) settingsHint.textContent = text || "Выбери режим, затем работай с кнопками в панели группы.";
    }

    function pickOrPlaceButton(id) {
      if (!pickedButtonId) {
        pickedButtonId = id;
        showMenu();
        return;
      }
      if (pickedButtonId === id) {
        pickedButtonId = null;
        showMenu();
        return;
      }
      moveButtonBefore(pickedButtonId, id);
      pickedButtonId = null;
      showMenu();
    }

    function moveButtonBefore(sourceId, targetId) {
      if (!sourceId || !targetId || sourceId === targetId) return;
      const order = orderedActions().map(item => item.id).filter(id => id !== sourceId);
      const targetIndex = order.indexOf(targetId);
      if (targetIndex < 0) return;
      order.splice(targetIndex, 0, sourceId);
      buttonSettings.order = order;
      saveButtonSettings();
      showMenu();
    }

    function textColorFor(hex) {
      const value = hex.replace("#", "");
      const r = parseInt(value.slice(0, 2), 16);
      const g = parseInt(value.slice(2, 4), 16);
      const b = parseInt(value.slice(4, 6), 16);
      return (r * 299 + g * 587 + b * 114) / 1000 > 145 ? "#172033" : "#ffffff";
    }

    function normalizedButtonSize(size) {
      if (size === "wide") return "large";
      return ["small", "normal", "large"].includes(size) ? size : "normal";
    }

    function showAction(id, title) {
      if (id !== "access" && !canUse(id)) {
        toast("Нет доступа к этой функции");
        return;
      }
      if (id === "access" && !ownerActionsAllowed) {
        toast("Доступ может менять только владелец");
        return;
      }
      document.getElementById("adminCard").classList.add("hidden");
      document.getElementById("actionCard").classList.remove("hidden");
      document.getElementById("actionTitle").textContent = title;
      const body = document.getElementById("actionBody");
      body.innerHTML = renderAction(id);
    }

    function renderAction(id) {
      if (!overview && id !== "premium") return "";
      if (id === "send") return sendMessageForm();
      if (id === "addReply") return canWrite(id) ? form("Сохранить", [["username", "input", "@username"], ["text", "textarea", "Ответ"]], "saveReply()") : writeLocked(id);
      if (id === "deleteReply") return list(overview.replies, item => `@${item.username}`, item => item.text, canWrite(id) ? item => `deleteReply('${encodeURIComponent(item.username)}')` : null);
      if (id === "triggers") return (canWrite("triggers.add") ? form("Добавить слово", [["trigger", "input", "Слово/фраза"], ["text", "textarea", "Ответ"]], "saveTrigger()") : writeLocked("triggers.add")) + list(overview.triggers, item => item.trigger, item => item.text, canWrite("triggers.delete") ? item => `deleteTrigger('${encodeURIComponent(item.trigger)}')` : null);
      if (id === "participants") return participantsForm();
      if (id === "checkAccess") return canWrite(id) ? `<button onclick="checkAccess()">Проверить доступ</button><div id="checkAccessResult" class="item" style="margin-top:12px"><div><div class="text">Нажми кнопку, чтобы проверить права бота в выбранной группе.</div></div></div>` : writeLocked(id);
      if (id === "giveaway") return canWrite("giveaway.settings") ? giveawayForm() : writeLocked(id);
      if (id === "restart") return canWrite(id) ? `<p class="muted">Перезапустит веб-панель API. Если бот запущен отдельно, его процесс не трогается.</p><button class="danger" onclick="restartPanel()">Да, перезапустить</button>` : writeLocked(id);
      if (id === "alarm") return alarmForm();
      if (id === "rollMute") return canWrite("rollMute.settings") ? rollMuteForm() : writeLocked(id);
      if (id === "quiet") return quietForm();
      if (id === "blacklist") return (canWrite("blacklist.add") ? form("Добавить слово", [["word", "input", "Слово"]], "addBlacklist()") : writeLocked("blacklist.add")) + list(overview.blacklist, item => item.word, () => "запрещено", canWrite("blacklist.delete") ? item => `deleteBlacklist('${encodeURIComponent(item.word)}')` : null);
      if (id === "quotes") return (canWrite("quotes.add") ? form("Добавить цитату", [["quote", "textarea", "Новая цитата"]], "addQuote()") : writeLocked("quotes.add")) + list([...overview.quotes].reverse(), item => `#${item.id}`, item => item.text, canWrite("quotes.delete") ? item => `deleteQuote(${item.id})` : null);
      if (id === "feedback") return canWrite("feedback.send") ? form("Отправить", [["feedbackText", "textarea", "Сообщение администраторам"]], "sendFeedback()") : writeLocked(id);
      if (id === "ads") return advertisementForm();
      if (id === "stars") return list(stars, item => item.full_name, item => `${item.amount} ${item.currency}`, null);
      if (id === "premium") return premiumSubscriptionsForm();
      if (id === "analytics") return ownerActionsAllowed ? analyticsForm() : `<p class="muted">Аналитика доступна только владельцу.</p>`;
      if (id === "mine") return mineForm();
      if (id === "logs") return logsForm();
      if (id === "access") return accessForm();
      if (id === "appSettings") return appSettingsForm();
      return "";
    }

    function accessForm() {
      setTimeout(loadPermissions, 0);
      return `
        <div class="form-stack">
          <div class="item">
            <div>
              <div class="title">Админы группы</div>
              <div class="text">Выбери админа, затем настрой чтение и изменение каждой кнопки.</div>
            </div>
          </div>
          <div id="permissionAdmins" class="row"></div>
          <div id="permissionFeatures" class="form-stack"></div>
        </div>
      `;
    }

    function sendMessageForm() {
      return `
        <textarea id="text" placeholder="Текст сообщения"></textarea>
        <div class="row">
          ${canWrite("send.text") ? `<button onclick="sendMessage()">Отправить текст</button>` : writeLocked("send.text")}
        </div>
        <div class="item">
          <div>
            <div class="title">Медиа</div>
            <div class="text">Фото, видео, аудио, документ или другой файл</div>
          </div>
        </div>
        <input id="mediaFile" type="file" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.txt">
        <input id="mediaCaption" placeholder="Подпись к медиа">
        ${canWrite("send.media") ? `<button onclick="sendPickedMedia()">Отправить медиа</button>` : writeLocked("send.media")}
        <div class="item">
          <div>
            <div class="title">Голосовое сообщение</div>
            <div class="text" id="voiceStatus">Нажми запись, затем стоп и отправка.</div>
          </div>
        </div>
        <div class="row">
          <button onclick="startVoiceRecord()">Записать</button>
          <button class="secondary" onclick="stopVoiceRecord()">Стоп</button>
          ${canWrite("send.voice") ? `<button onclick="sendVoiceRecord()">Отправить голос</button>` : writeLocked("send.voice")}
        </div>
      `;
    }

    function appSettingsForm() {
      const settings = loadAppSettings();
      return `
        <div class="app-settings-form">
        <label>Тема
          <select id="themeSelect">
            <option value="light" ${settings.theme === "light" ? "selected" : ""}>Светлая</option>
            <option value="dark" ${settings.theme === "dark" ? "selected" : ""}>Темная</option>
            <option value="oled" ${settings.theme === "oled" ? "selected" : ""}>OLED</option>
            <option value="green" ${settings.theme === "green" ? "selected" : ""}>Зеленая</option>
          </select>
        </label>
        <label>Город для погоды
          <input id="weatherCityInput" placeholder="Например: Кривой Рог" value="${escapeHtml(settings.weatherCity || "")}">
        </label>
        <label>Обновлять погоду, минут
          <input id="weatherRefreshInput" type="number" min="0" max="1440" placeholder="Например: 30" value="${escapeHtml(String(settings.weatherRefreshMinutes ?? 30))}">
        </label>
        <label>Фоновая картинка
          <input id="bgImageInput" type="file" accept="image/*">
        </label>
        <div class="row">
          <button onclick="saveAppSettings()">Сохранить</button>
          <button class="secondary" onclick="refreshWeather(true)">Обновить погоду</button>
          <button class="secondary" onclick="clearBackgroundImage()">Убрать фон</button>
        </div>
        </div>
      `;
    }

    function form(button, fields, submit) {
      return `<div class="form-stack">` + fields.map(([id, type, placeholder, value]) => {
        const safeValue = escapeHtml(String(value ?? ""));
        return type === "textarea"
          ? `<textarea id="${id}" placeholder="${placeholder}">${safeValue}</textarea>`
          : `<input id="${id}" placeholder="${placeholder}" value="${safeValue}">`;
      }).join("") + `<button onclick="${submit}">${button}</button></div>`;
    }

    function alarmForm() {
      const enabled = overview.alarm.enabled === 1;
      return `
        ${canWrite("alarm.toggle") ? `<button onclick="toggleAlarm(${!enabled})">${enabled ? "Выключить режим" : "Включить режим"}</button>` : writeLocked("alarm.toggle")}
        ${canWrite("alarm.text") ? form("Сохранить тексты", [
          ["alarmText", "textarea", "Текст тревоги", overview.alarm.alarm_text || ""],
          ["clearText", "textarea", "Текст отбоя", overview.alarm.clear_text || ""]
        ], "saveAlarmTexts()") : writeLocked("alarm.text")}
      `;
    }

    function rollMuteForm() {
      return `
        <div class="form-stack">
          <label>Мут, минут
            <input id="mute" placeholder="Например: 60" value="${escapeHtml(String(overview.rollMute.mute_minutes || 60))}">
          </label>
          <label>Ожидание между roll mute, минут
            <input id="cooldown" placeholder="Например: 30" value="${escapeHtml(String(overview.rollMute.cooldown_minutes || 30))}">
          </label>
          <button onclick="saveRollMute()">Сохранить</button>
        </div>
      `;
    }

    function giveawayForm() {
      const settings = overview.giveaway || {};
      const birthdays = list(
        overview.birthdays || [],
        item => `${String(item.day).padStart(2, "0")}.${String(item.month).padStart(2, "0")}`,
        item => item.text,
        canWrite("giveaway.birthdays") ? item => `deleteBirthday(${item.id})` : null
      );
      return `
        <h2>Розыгрыш</h2>
        ${canWrite("giveaway.settings") ? form("Сохранить розыгрыш", [
        ["giveawayTrigger", "input", "Фраза вызова", settings.trigger || ""],
        ["giveawayCount", "input", "Количество победителей", settings.winners_count || 1],
        ["giveawayTitle", "input", "Название", settings.title || ""],
        ], "saveGiveaway()") : writeLocked("giveaway.settings")}
        <h2>Дни рождения</h2>
        ${canWrite("giveaway.birthdays") ? form("Добавить день рождения", [
          ["birthdayDay", "input", "День"],
          ["birthdayMonth", "input", "Месяц"],
          ["birthdayText", "input", "Имя или текст поздравления"]
        ], "addBirthday()") : writeLocked("giveaway.birthdays")}
        ${birthdays}
      `;
    }

    function quietForm() {
      const media = overview.quiet.media_type || "не выбрано";
      return `
        <h2>Замуть того</h2>
        ${canWrite("quiet.manual") ? form("Замутить", [
          ["quietTarget", "input", "@username или User ID"],
          ["quietMinutes", "input", "Минуты"],
          ["quietReason", "input", "Причина"]
        ], "quietManual()") : writeLocked("quiet.manual")}
        <h2>Текст ответа</h2>
        ${canWrite("quiet.text") ? form("Сохранить текст", [["quiet", "textarea", "Текст ответа", overview.quiet.reply_text || ""]], "saveQuiet()") : writeLocked("quiet.text")}
        <h2>Гиф/голос/аудио</h2>
        <p class="muted">Сейчас: ${escapeHtml(media)}</p>
        <input id="quietMediaFile" type="file" accept="image/gif,audio/*,.ogg,.oga,.opus,.mp3,.m4a">
        <label class="row"><input id="quietMediaAsVoice" type="checkbox"> <span>Сохранить как голосовое</span></label>
        ${canWrite("quiet.mediaSave") ? `<button onclick="saveQuietMedia()">Сохранить медиа</button>` : writeLocked("quiet.mediaSave")}
        ${canWrite("quiet.mediaDelete") ? `<button class="danger" onclick="deleteQuietMedia()">Удалить медиа</button>` : writeLocked("quiet.mediaDelete")}
      `;
    }

    function advertisementScheduleFields(suffix, ad = {}) {
      const duration = ad.duration_type || "once";
      const topics = overview.topics || [];
      const topicOptions = [
        `<option value="" ${ad.topic_thread_id == null ? "selected" : ""}>Основной чат / без темы</option>`,
        ...topics.map(topic => `<option value="${topic.thread_id}" ${Number(ad.topic_thread_id) === Number(topic.thread_id) ? "selected" : ""}>${escapeHtml(topic.title)}</option>`)
      ].join("");
      return `
        <label class="row"><input id="advertisement-enabled-${suffix}" type="checkbox" ${ad.enabled === 0 ? "" : "checked"}> <span>Публикация включена</span></label>
        <label>Время первой публикации
          <input id="advertisement-start-${suffix}" type="time" value="${escapeHtml(ad.start_time || "09:00")}">
        </label>
        <label>Длительность рекламы
          <select id="advertisement-duration-${suffix}" onchange="updateAdvertisementDuration('${suffix}')">
            <option value="once" ${duration === "once" ? "selected" : ""}>Опубликовать один раз</option>
            <option value="day" ${duration === "day" ? "selected" : ""}>Публиковать один день</option>
            <option value="unlimited" ${duration === "unlimited" ? "selected" : ""}>Публиковать бессрочно</option>
          </select>
        </label>
        <label>Тема публикации
          <select id="advertisement-topic-${suffix}">${topicOptions}</select>
        </label>
        <label id="advertisement-interval-wrap-${suffix}" style="${duration === "once" ? "display:none" : ""}">Частота публикации, минут
          <input id="advertisement-interval-${suffix}" type="number" min="1" max="43200" value="${escapeHtml(String(ad.interval_minutes || 180))}">
        </label>
      `;
    }

    function advertisementForm() {
      const ads = overview.advertisements || [];
      const topics = overview.topics || [];
      const topicEditor = topics.length && canWrite("ads.settings") ? `
        <h2>Названия тем</h2>
        <div class="form-stack">
          ${topics.map(topic => `
            <div class="row">
              <input id="topic-title-${topic.thread_id}" value="${escapeHtml(topic.title)}" placeholder="Название темы">
              <button class="secondary" onclick="renameTopic(${topic.thread_id})">Сохранить название</button>
            </div>
          `).join("")}
        </div>
        <div style="height:18px"></div>
      ` : "";
      if (!ads.length) {
        return canWrite("ads.add") && canWrite("ads.settings")
          ? `${topicEditor}
            <h2>Добавить рекламу</h2>
            <div class="form-stack">
              <textarea id="advertisementText" placeholder="Текст рекламы"></textarea>
              <label>Фото и видео, до 10 файлов
                <input id="advertisementFiles" type="file" accept="image/jpeg,image/png,image/webp,video/*" multiple>
              </label>
              ${advertisementScheduleFields("new")}
              <div class="row">
                <button onclick="addAdvertisement('now')">Сохранить и запустить сейчас</button>
                <button class="secondary" onclick="addAdvertisement('scheduled')">Сохранить по времени</button>
              </div>
            </div>
          `
          : writeLocked(canWrite("ads.add") ? "ads.settings" : "ads.add");
      }
      const adRows = ads.map((ad, index) => `
        <div class="item" style="display:block">
          <div class="title">Реклама ${index + 1}</div>
          <div class="muted" style="margin-top:6px">Вложения: ${escapeHtml((ad.attachments || []).map(item => item.filename || item.media_type).join(", ") || "нет")}</div>
          <div class="muted" style="margin-top:6px">Запуск: ${ad.start_mode === "now" ? "сразу после сохранения" : escapeHtml(ad.scheduled_at || "время не назначено")} · Первый выход: ${escapeHtml(ad.first_sent_at || "ещё не выходила")} · Последний: ${escapeHtml(ad.last_sent_at || "ещё не выходила")}</div>
          ${ad.last_error ? `<div style="margin-top:6px;color:#ef4444">Ошибка отправки: ${escapeHtml(ad.last_error)}</div>` : ""}
          <textarea id="advertisement-${ad.id}" style="margin-top:10px">${escapeHtml(ad.text)}</textarea>
          ${canWrite("ads.edit") && canWrite("ads.settings") ? `
            <label style="display:block;margin-top:10px">Заменить вложения
              <input id="advertisement-files-${ad.id}" type="file" accept="image/jpeg,image/png,image/webp,video/*" multiple>
            </label>
            <label class="row"><input id="advertisement-remove-${ad.id}" type="checkbox"> <span>Удалить текущие вложения</span></label>
            ${advertisementScheduleFields(ad.id, ad)}
          ` : ""}
          <div class="row" style="margin-top:10px">
            ${canWrite("ads.edit") && canWrite("ads.settings") ? `
              <button onclick="editAdvertisement(${ad.id}, 'now')">Сохранить и запустить сейчас</button>
              <button class="secondary" onclick="editAdvertisement(${ad.id}, 'scheduled')">Сохранить по времени</button>
            ` : ""}
            ${canWrite("ads.delete") ? `<button class="danger" onclick="deleteAdvertisement(${ad.id})">Удалить</button>` : ""}
          </div>
        </div>
      `).join("");
      return `
        ${topicEditor}
        ${adRows}
        <div style="height:18px"></div>
        ${canWrite("ads.add") && canWrite("ads.settings") ? `
          <h2>Добавить ещё рекламу</h2>
          <div class="form-stack">
            <textarea id="advertisementText" placeholder="Текст новой рекламы"></textarea>
            <label>Фото и видео, до 10 файлов
              <input id="advertisementFiles" type="file" accept="image/jpeg,image/png,image/webp,video/*" multiple>
            </label>
            ${advertisementScheduleFields("new")}
            <div class="row">
              <button onclick="addAdvertisement('now')">Сохранить и запустить сейчас</button>
              <button class="secondary" onclick="addAdvertisement('scheduled')">Сохранить по времени</button>
            </div>
          </div>
        ` : writeLocked(canWrite("ads.add") ? "ads.settings" : "ads.add")}
      `;
    }

    function participantsForm() {
      setTimeout(() => loadParticipantTop("day"), 0);
      return `
        <div class="row">
          <button class="secondary" onclick="loadParticipantTop('day')">День</button>
          <button class="secondary" onclick="loadParticipantTop('week')">Неделя</button>
          <button class="secondary" onclick="loadParticipantTop('month')">Месяц</button>
          <button class="secondary" onclick="loadParticipantTop('all')">Все время</button>
        </div>
        <div id="participantTopResult" style="margin-top:12px"></div>
      `;
    }

    function logsForm() {
      setTimeout(loadAuditLogs, 0);
      return `<div id="auditLogs"><p class="muted">Загрузка журнала...</p></div>`;
    }

    async function loadAuditLogs() {
      const box = document.getElementById("auditLogs");
      if (!box) return;
      const data = await api(`/admin/chats/${selectedChatId}/logs?limit=100`);
      box.innerHTML = (data.items || []).map(item => `
        <div class="item" style="display:block">
          <div class="title">${escapeHtml(item.action)}</div>
          <div class="text">${escapeHtml(item.actor_username ? "@" + item.actor_username : (item.actor_name || ("ID " + (item.actor_id || "неизвестен"))))}</div>
          <div class="muted">${escapeHtml(item.created_at)} · ${escapeHtml(item.source)}</div>
          ${item.details ? `<div class="muted">${escapeHtml(item.details)}</div>` : ""}
        </div>
      `).join("") || `<p class="muted">Журнал пока пуст.</p>`;
    }

    function mineForm() {
      const totalPages = Math.max(1, Math.ceil((digPlayers.total || 0) / (digPlayers.perPage || 20)));
      const start = ((digPlayers.page || 1) - 1) * (digPlayers.perPage || 20);
      const rows = (digPlayers.items || []).map((p, i) =>
        `<div class="item"><div><div class="title">${start + i + 1}. ${escapeHtml(p.full_name)}</div><div class="text">${p.total_depth} м · ${p.coins} монет · доп. копаний: ${p.extraDigs || 0}</div></div></div>`
      ).join("");
      const pager = `
        <div class="row" style="justify-content: space-between">
          <button class="secondary" onclick="changeDigPage(${Math.max(1, (digPlayers.page || 1) - 1)})" ${(digPlayers.page || 1) <= 1 ? "disabled" : ""}>Назад</button>
          <span class="muted">Страница ${digPlayers.page || 1} из ${totalPages} · игроков: ${digPlayers.total || 0}</span>
          <button class="secondary" onclick="changeDigPage(${Math.min(totalPages, (digPlayers.page || 1) + 1)})" ${(digPlayers.page || 1) >= totalPages ? "disabled" : ""}>Дальше</button>
        </div>
      `;
      const grantForm = ownerActionsAllowed ? form("Выдать бонус", [
        ["userId", "input", "User ID"],
        ["coins", "input", "Монеты (+/-)"],
        ["luck", "input", "Удача 0-100"],
        ["extraDigs", "input", "Доп. копания (+/-)"]
      ], "grantDig()") : `<p class="muted">Начислять или забирать ресурсы может только главный админ бота.</p>`;
      const ticketGrantForm = ownerOnlyActionsAllowed ? `
        <div class="form-stack" style="margin-top:16px">
          <h2>Выдать билеты</h2>
          <p class="muted">Доступно только владельцу бота. Укажи User ID игрока шахты.</p>
          <input id="ticketUserId" placeholder="User ID">
          <input id="goldenTickets" type="number" min="1" placeholder="Количество золотых билетов">
          <input id="superPasses" type="number" min="1" placeholder="Количество супер-игр">
          <button onclick="grantTickets()">Выдать билеты</button>
        </div>
      ` : "";
      return grantForm + ticketGrantForm + `<h2 style="margin-top:16px">Игроки шахты</h2>${pager}${rows || `<p class="muted">Пока нет игроков.</p>`}${pager}`;
    }

    function premiumSubscriptionsForm() {
      const rows = (premiumSubscriptions.items || []).map(item => `
        <div class="item" style="display:block">
          <div class="title">${escapeHtml(item.username ? "@" + item.username : "ID " + item.user_id)}</div>
          <div class="text">${escapeHtml(item.planTitle)} · ${item.active ? "активна" : "не активна"}</div>
          <div class="muted">Начало: ${escapeHtml(item.started_at)}</div>
          <div class="muted">Окончание: ${escapeHtml(item.expires_at)}</div>
        </div>
      `).join("");
      const grantForm = ownerActionsAllowed ? `
        <div class="form-stack">
          <h2>Выдать Premium</h2>
          <input id="premiumUserId" placeholder="User ID">
          <select id="premiumPlan">
            <option value="basic">Базовый Premium - 50 Stars</option>
            <option value="extended">Расширенный Premium - 100 Stars</option>
          </select>
          <input id="premiumDays" placeholder="Дней" value="30">
          <button onclick="grantPremium()">Выдать Premium</button>
        </div>
      ` : "";
      return `${grantForm}<h2 style="margin-top:16px">Подписки</h2><p class="muted">Подписок: ${premiumSubscriptions.total || 0}</p>${rows || `<p class="muted">Покупок Premium пока нет.</p>`}`;
    }

    function analyticsForm() {
      const summary = analyticsData.summary || {};
      const byApp = (summary.byApp || []).map(item => `${escapeHtml(item.app)}: <b>${item.total}</b>`).join(" · ") || "пока нет";
      const byType = (summary.byType || []).map(item => `${escapeHtml(item.event_type)}: <b>${item.total}</b>`).join(" · ") || "пока нет";
      const topErrors = (summary.topErrors || []).map(item => `
        <div class="item" style="display:block">
          <div class="title">${escapeHtml(item.app)} · ${escapeHtml(item.error_type || "error")}</div>
          <div class="text">${escapeHtml(item.endpoint || "без endpoint")} · ${item.total} раз</div>
          <div class="muted">Последний раз: ${escapeHtml(item.last_at || "")}</div>
        </div>
      `).join("");
      const items = (analyticsData.items || []).slice(0, 30).map(item => `
        <div class="item" style="display:block">
          <div class="title">${escapeHtml(item.app)} · ${escapeHtml(item.event_name)}</div>
          <div class="text">${escapeHtml(item.manufacturer || "")} ${escapeHtml(item.model || "")} · Android ${escapeHtml(item.android_version || "")}</div>
          <div class="muted">${escapeHtml(item.event_type)} · ${escapeHtml(item.created_at)}${item.endpoint ? " · " + escapeHtml(item.endpoint) : ""}</div>
          ${item.message ? `<div class="muted">${escapeHtml(item.message)}</div>` : ""}
        </div>
      `).join("");
      return `
        <div class="item" style="display:block">
          <div class="title">Сводка</div>
          <div class="text">Событий: <b>${summary.total || 0}</b> · устройств: <b>${summary.devices || 0}</b></div>
          <div class="muted">Приложения: ${byApp}</div>
          <div class="muted">Типы: ${byType}</div>
        </div>
        <button class="secondary" onclick="refreshAnalytics()">Обновить</button>
        <h2 style="margin-top:16px">Частые ошибки</h2>
        ${topErrors || `<p class="muted">Ошибок пока нет.</p>`}
        <h2 style="margin-top:16px">Последние события</h2>
        ${items || `<p class="muted">Событий пока нет.</p>`}
      `;
    }

    function list(items, titleFn, bodyFn, deleteCall) {
      if (!items || items.length === 0) return `<p class="muted">Пусто.</p>`;
      return items.map(item => `
        <div class="item">
          <div>
            <div class="title">${escapeHtml(titleFn(item))}</div>
            <div class="text">${escapeHtml(bodyFn(item))}</div>
          </div>
          ${deleteCall ? `<button class="danger" onclick="${deleteCall(item)}">Удалить</button>` : ""}
        </div>
      `).join("");
    }

    async function afterAction(message) {
      toast(message);
      await selectChat(selectedChatId);
      document.getElementById("actionCard").classList.add("hidden");
    }

    function afterSendAction(message) {
      toast(message);
    }

    async function sendMessage() {
      await api(`/admin/chats/${selectedChatId}/message`, { method: "POST", body: JSON.stringify({ text: val("text") }) });
      const text = document.getElementById("text");
      if (text) text.value = "";
      afterSendAction("Отправлено");
    }
    async function sendPickedMedia() {
      const input = document.getElementById("mediaFile");
      if (!input.files || !input.files[0]) {
        toast("Выбери файл");
        return;
      }
      const file = input.files[0];
      const dataBase64 = await fileToBase64(file);
      await api(`/admin/chats/${selectedChatId}/media`, {
        method: "POST",
        body: JSON.stringify({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          dataBase64,
          caption: val("mediaCaption")
        })
      });
      input.value = "";
      const caption = document.getElementById("mediaCaption");
      if (caption) caption.value = "";
      afterSendAction("Медиа отправлено");
    }
    async function startVoiceRecord() {
      if (window.AndroidVoice) {
        nativeVoiceBase64 = null;
        const started = window.AndroidVoice.startRecord();
        document.getElementById("voiceStatus").textContent = started ? "Идет запись..." : "Не удалось начать запись";
        if (!started) toast("Нет доступа к микрофону");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recordedChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = event => {
          if (event.data.size > 0) recordedChunks.push(event.data);
        };
        mediaRecorder.onstop = () => stream.getTracks().forEach(track => track.stop());
        mediaRecorder.start();
        document.getElementById("voiceStatus").textContent = "Идет запись...";
      } catch (error) {
        toast("Нет доступа к микрофону");
      }
    }
    function stopVoiceRecord() {
      if (window.AndroidVoice) {
        const data = window.AndroidVoice.stopRecord();
        if (data) {
          nativeVoiceBase64 = data;
          nativeVoiceMime = window.AndroidVoice.getMimeType();
          nativeVoiceFilename = window.AndroidVoice.getFileName();
          document.getElementById("voiceStatus").textContent = "Запись готова к отправке.";
        } else {
          toast("Не удалось сохранить голос");
        }
        return;
      }
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        document.getElementById("voiceStatus").textContent = "Запись готова к отправке.";
      }
    }
    async function sendVoiceRecord() {
      if (nativeVoiceBase64) {
        await api(`/admin/chats/${selectedChatId}/media`, {
          method: "POST",
          body: JSON.stringify({
            filename: nativeVoiceFilename,
            mimeType: nativeVoiceMime,
            dataBase64: nativeVoiceBase64,
            asVoice: true
          })
        });
        nativeVoiceBase64 = null;
        const status = document.getElementById("voiceStatus");
        if (status) status.textContent = "Нажми запись, затем стоп и отправка.";
        afterSendAction("Голос отправлен");
        return;
      }
      if (!recordedChunks.length) {
        toast("Сначала запиши голос");
        return;
      }
      const blob = new Blob(recordedChunks, { type: recordedChunks[0].type || "audio/webm" });
      const dataBase64 = await blobToBase64(blob);
      await api(`/admin/chats/${selectedChatId}/media`, {
        method: "POST",
        body: JSON.stringify({
          filename: "voice.webm",
          mimeType: blob.type || "audio/webm",
          dataBase64,
          asVoice: true
        })
      });
      recordedChunks = [];
      const status = document.getElementById("voiceStatus");
      if (status) status.textContent = "Нажми запись, затем стоп и отправка.";
      afterSendAction("Голос отправлен");
    }
    async function sendFeedback() {
      await api(`/admin/feedback`, { method: "POST", body: JSON.stringify({ text: val("feedbackText") }) });
      afterAction("Обратная связь отправлена");
    }
    async function saveReply() {
      await api(`/admin/chats/${selectedChatId}/replies`, { method: "POST", body: JSON.stringify({ username: val("username"), text: val("text") }) });
      afterAction("Ответ сохранен");
    }
    async function deleteReply(username) {
      await api(`/admin/chats/${selectedChatId}/replies/${username}`, { method: "DELETE" });
      afterAction("Ответ удален");
    }
    async function saveTrigger() {
      await api(`/admin/chats/${selectedChatId}/triggers`, { method: "POST", body: JSON.stringify({ trigger: val("trigger"), text: val("text") }) });
      afterAction("Триггер сохранен");
    }
    async function deleteTrigger(trigger) {
      await api(`/admin/chats/${selectedChatId}/triggers/${trigger}`, { method: "DELETE" });
      afterAction("Триггер удален");
    }
    async function checkAccess() {
      const result = await api(`/admin/chats/${selectedChatId}/check-access`, { method: "POST" });
      document.getElementById("checkAccessResult").innerHTML = `
        <div>
          <div class="title">${escapeHtml(result.title || "")}</div>
          <div class="text">Статус: ${escapeHtml(result.status || "")}</div>
          <div class="text">Удалять сообщения: ${result.canDeleteMessages ? "да" : "нет"}</div>
          <div class="text">Ограничивать участников: ${result.canRestrictMembers ? "да" : "нет"}</div>
          <div class="text">Приглашать пользователей: ${result.canInviteUsers ? "да" : "нет"}</div>
        </div>
      `;
    }
    async function restartPanel() {
      if (!confirm("Перезапустить веб-панель API?")) return;
      await api(`/admin/restart`, { method: "POST" });
      toast("Перезапуск...");
      setTimeout(() => location.reload(), 2500);
    }
    async function toggleAlarm(enabled) {
      await api(`/admin/chats/${selectedChatId}/alarm`, { method: "POST", body: JSON.stringify({ enabled }) });
      afterAction("Режим обновлен");
    }
    async function saveAlarmTexts() {
      await api(`/admin/chats/${selectedChatId}/alarm`, { method: "POST", body: JSON.stringify({ alarmText: val("alarmText"), clearText: val("clearText") }) });
      afterAction("Тексты сохранены");
    }
    async function saveRollMute() {
      await api(`/admin/chats/${selectedChatId}/roll-mute`, { method: "POST", body: JSON.stringify({ muteMinutes: Number(val("mute")), cooldownMinutes: Number(val("cooldown")) }) });
      afterAction("Roll mute сохранен");
    }
    async function saveQuiet() {
      await api(`/admin/chats/${selectedChatId}/quiet`, { method: "POST", body: JSON.stringify({ replyText: val("quiet") }) });
      afterAction("Ответ сохранен");
    }
    async function quietManual() {
      await api(`/admin/chats/${selectedChatId}/quiet/manual`, {
        method: "POST",
        body: JSON.stringify({
          target: val("quietTarget"),
          minutes: Number(val("quietMinutes")),
          reason: val("quietReason")
        })
      });
      afterAction("Пользователь замучен");
    }
    async function saveQuietMedia() {
      const file = document.getElementById("quietMediaFile").files[0];
      if (!file) {
        toast("Выбери GIF, голос или аудио");
        return;
      }
      const dataBase64 = await blobToBase64(file);
      await api(`/admin/chats/${selectedChatId}/quiet/media`, {
        method: "POST",
        body: JSON.stringify({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          dataBase64,
          asVoice: document.getElementById("quietMediaAsVoice").checked
        })
      });
      afterAction("Медиа сохранено");
    }
    async function deleteQuietMedia() {
      await api(`/admin/chats/${selectedChatId}/quiet/media`, { method: "DELETE" });
      afterAction("Медиа удалено");
    }
    async function saveGiveaway() {
      await api(`/admin/chats/${selectedChatId}/giveaway`, {
        method: "POST",
        body: JSON.stringify({
          trigger: val("giveawayTrigger"),
          winnersCount: Number(val("giveawayCount")),
          title: val("giveawayTitle")
        })
      });
      afterAction("Розыгрыш сохранен");
    }
    async function addBirthday() {
      await api(`/admin/chats/${selectedChatId}/birthdays`, {
        method: "POST",
        body: JSON.stringify({
          day: Number(val("birthdayDay")),
          month: Number(val("birthdayMonth")),
          text: val("birthdayText")
        })
      });
      afterAction("День рождения добавлен");
    }
    async function deleteBirthday(id) {
      await api(`/admin/chats/${selectedChatId}/birthdays/${id}`, { method: "DELETE" });
      afterAction("День рождения удален");
    }
    async function addAdvertisement(startMode) {
      const attachments = await advertisementFilesPayload("advertisementFiles");
      await api(`/admin/chats/${selectedChatId}/advertisements`, {
        method: "POST",
        body: JSON.stringify({ text: val("advertisementText"), attachments, ...advertisementSchedulePayload("new", startMode) })
      });
      afterAction("Реклама добавлена");
    }
    async function editAdvertisement(id, startMode) {
      const attachments = await advertisementFilesPayload(`advertisement-files-${id}`);
      const remove = document.getElementById(`advertisement-remove-${id}`).checked;
      await api(`/admin/chats/${selectedChatId}/advertisements/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          text: val(`advertisement-${id}`),
          attachments,
          replaceAttachments: remove || attachments.length > 0,
          ...advertisementSchedulePayload(id, startMode)
        })
      });
      afterAction("Реклама обновлена");
    }
    async function advertisementFilesPayload(inputId) {
      const input = document.getElementById(inputId);
      const files = input ? Array.from(input.files || []) : [];
      if (files.length > 10) {
        throw new Error("Можно выбрать не больше 10 вложений");
      }
      if (files.some(file => !file.type.startsWith("image/") && !file.type.startsWith("video/"))) {
        throw new Error("В рекламу можно добавить только фото и видео");
      }
      return Promise.all(files.map(async file => ({
        filename: file.name,
        mimeType: file.type || "application/octet-stream",
        dataBase64: await fileToBase64(file)
      })));
    }
    function advertisementSchedulePayload(suffix, startMode) {
      const durationType = val(`advertisement-duration-${suffix}`);
      return {
        enabled: document.getElementById(`advertisement-enabled-${suffix}`).checked,
        startMode,
        startTime: val(`advertisement-start-${suffix}`),
        intervalMinutes: durationType === "once" ? 1 : Number(val(`advertisement-interval-${suffix}`)),
        durationType,
        topicThreadId: val(`advertisement-topic-${suffix}`) === "" ? null : Number(val(`advertisement-topic-${suffix}`))
      };
    }
    function updateAdvertisementDuration(suffix) {
      const duration = val(`advertisement-duration-${suffix}`);
      document.getElementById(`advertisement-interval-wrap-${suffix}`).style.display = duration === "once" ? "none" : "";
    }
    async function deleteAdvertisement(id) {
      await api(`/admin/chats/${selectedChatId}/advertisements/${id}`, { method: "DELETE" });
      afterAction("Реклама удалена");
    }
    async function renameTopic(threadId) {
      await api(`/admin/chats/${selectedChatId}/topics/${threadId}`, {
        method: "PUT",
        body: JSON.stringify({ title: val(`topic-title-${threadId}`) })
      });
      afterAction("Название темы сохранено");
    }
    async function loadParticipantTop(period) {
      const box = document.getElementById("participantTopResult");
      if (!box) return;
      const data = await api(`/admin/chats/${selectedChatId}/participants/top?period=${period}&limit=20`);
      const names = { day: "день", week: "неделю", month: "месяц", all: "все время" };
      const rows = (data.items || []).map((item, index) => `
        <div class="item">
          <div>
            <div class="title">${index + 1}. ${escapeHtml(item.username ? "@" + item.username : item.full_name)}</div>
            <div class="text">${item.messages_count} сообщений</div>
          </div>
        </div>
      `).join("");
      box.innerHTML = `<h2>Топ за ${names[period] || period}</h2>${rows || `<p class="muted">Пока нет данных. Топ начнет заполняться с новых сообщений после обновления.</p>`}`;
    }
    async function addBlacklist() {
      await api(`/admin/chats/${selectedChatId}/blacklist`, { method: "POST", body: JSON.stringify({ word: val("word") }) });
      afterAction("Слово добавлено");
    }
    async function deleteBlacklist(word) {
      await api(`/admin/chats/${selectedChatId}/blacklist/${word}`, { method: "DELETE" });
      afterAction("Слово удалено");
    }
    async function addQuote() {
      await api(`/admin/chats/${selectedChatId}/quotes`, { method: "POST", body: JSON.stringify({ text: val("quote") }) });
      afterAction("Цитата добавлена");
    }
    async function deleteQuote(id) {
      await api(`/admin/chats/${selectedChatId}/quotes/${id}`, { method: "DELETE" });
      afterAction("Цитата удалена");
    }
    async function changeDigPage(page) {
      digPlayers = await api(`/admin/dig/players?page=${page}&per_page=20`);
      document.getElementById("actionBody").innerHTML = mineForm();
    }
    async function refreshAnalytics() {
      analyticsData = await api("/admin/analytics?limit=80");
      document.getElementById("actionBody").innerHTML = analyticsForm();
    }
    async function grantDig() {
      const payload = { userId: Number(val("userId")), clearCooldown: true };
      if (val("coins")) payload.coins = Number(val("coins"));
      if (val("luck")) payload.luck = Number(val("luck"));
      if (val("extraDigs")) payload.extraDigs = Number(val("extraDigs"));
      await api(`/admin/dig/grant`, { method: "POST", body: JSON.stringify(payload) });
      digTop = await api("/admin/dig/top");
      digPlayers = await api(`/admin/dig/players?page=${digPlayers.page || 1}&per_page=20`);
      afterAction("Игрок обновлен");
    }

    async function grantTickets() {
      const payload = { userId: Number(val("ticketUserId")), clearCooldown: false };
      if (val("goldenTickets")) payload.goldenTickets = Number(val("goldenTickets"));
      if (val("superPasses")) payload.superPasses = Number(val("superPasses"));
      if (payload.goldenTickets === undefined && payload.superPasses === undefined) {
        throw new Error("Укажи количество билетов или доступов.");
      }
      await api(`/admin/dig/grant`, { method: "POST", body: JSON.stringify(payload) });
      digPlayers = await api(`/admin/dig/players?page=${digPlayers.page || 1}&per_page=20`);
      document.getElementById("actionBody").innerHTML = mineForm();
      toast("Билеты выданы");
    }

    async function grantPremium() {
      const payload = {
        userId: Number(val("premiumUserId")),
        plan: document.getElementById("premiumPlan").value,
        days: Number(val("premiumDays") || 30)
      };
      await api(`/admin/premium/grant`, { method: "POST", body: JSON.stringify(payload) });
      premiumSubscriptions = await api("/admin/premium/subscriptions");
      document.getElementById("actionBody").innerHTML = premiumSubscriptionsForm();
      toast("Premium выдан");
    }

    async function saveAppSettings() {
      const settings = loadAppSettings();
      settings.theme = document.getElementById("themeSelect").value;
      settings.weatherCity = document.getElementById("weatherCityInput").value.trim();
      settings.weatherRefreshMinutes = Math.max(0, Math.min(1440, Number(document.getElementById("weatherRefreshInput").value || 0)));
      const input = document.getElementById("bgImageInput");
      if (input.files && input.files[0]) {
        settings.background = await imageToBackgroundDataUrl(input.files[0]);
      }
      localStorage.setItem("appSettings", JSON.stringify(settings));
      applyAppSettings();
      await refreshWeather();
      scheduleWeatherRefresh();
      toast("Настройки сохранены");
    }

    function clearBackgroundImage() {
      const settings = loadAppSettings();
      delete settings.background;
      localStorage.setItem("appSettings", JSON.stringify(settings));
      applyAppSettings();
      toast("Фон убран");
    }

    function loadAppSettings() {
      try {
        return JSON.parse(localStorage.getItem("appSettings") || "{}");
      } catch (_) {
        return {};
      }
    }

    function applyAppSettings() {
      const settings = loadAppSettings();
      document.body.classList.toggle("theme-dark", settings.theme === "dark");
      document.body.classList.toggle("theme-green", settings.theme === "green");
      document.body.classList.toggle("theme-oled", settings.theme === "oled");
      if (window.AndroidApp) {
        window.AndroidApp.setThemeBars(settings.theme || "light");
      }
      if (settings.background) {
        document.body.style.setProperty("--bg-image", `url("${settings.background}")`);
        const scrim = settings.theme === "oled" ? "0.78" : settings.theme === "dark" ? "0.68" : settings.theme === "green" ? "0.74" : "0.76";
        document.body.style.setProperty("--bg-scrim", scrim);
      } else {
        document.body.style.removeProperty("--bg-image");
        document.body.style.removeProperty("--bg-scrim");
      }
    }

    function weatherDescription(code) {
      const map = {
        0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
        45: "Туман", 48: "Туман", 51: "Слабая морось", 53: "Морось", 55: "Сильная морось",
        61: "Небольшой дождь", 63: "Дождь", 65: "Сильный дождь", 71: "Небольшой снег",
        73: "Снег", 75: "Сильный снег", 80: "Небольшой ливень", 81: "Ливень",
        82: "Сильный ливень", 95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза"
      };
      return map[Number(code)] || "Нет данных";
    }

    async function refreshWeather(manual = false) {
      const settings = loadAppSettings();
      const city = (settings.weatherCity || "").trim();
      const card = document.getElementById("weatherCard");
      const target = document.getElementById("weatherStatus");
      if (!city) {
        card.classList.add("hidden");
        return;
      }
      card.classList.remove("hidden");
      if (manual) target.textContent = "Обновляю погоду...";
      try {
        const data = await api(`/admin/weather?q=${encodeURIComponent(city)}`);
        const updated = data.updatedAt ? new Date(data.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
        target.innerHTML = `
          <b>${escapeHtml(data.location || city)}</b><br>
          ${escapeHtml(weatherDescription(data.weatherCode))} · <b>${escapeHtml(String(data.temperature ?? "?"))}°C</b>
          <span class="muted">ощущается ${escapeHtml(String(data.apparentTemperature ?? "?"))}°C</span><br>
          Ветер: <b>${escapeHtml(String(data.windSpeed ?? "?"))} км/ч</b> · Влажность: <b>${escapeHtml(String(data.humidity ?? "?"))}%</b>
          ${updated ? `<br><span class="muted">Обновлено: ${escapeHtml(updated)}</span>` : ""}
        `;
      } catch (error) {
        target.textContent = `Не удалось загрузить погоду: ${error.message || error}`;
      }
    }

    function scheduleWeatherRefresh() {
      if (weatherTimer) {
        clearInterval(weatherTimer);
        weatherTimer = null;
      }
      const settings = loadAppSettings();
      const minutes = Number(settings.weatherRefreshMinutes || 0);
      if (!settings.weatherCity || minutes <= 0) return;
      weatherTimer = setInterval(() => refreshWeather(), minutes * 60 * 1000);
    }

    function fileToDataUrl(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    }

    async function imageToBackgroundDataUrl(file) {
      const source = await fileToDataUrl(file);
      return new Promise(resolve => {
        const image = new Image();
        image.onload = () => {
          const maxSide = 1600;
          const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(image.width * scale));
          canvas.height = Math.max(1, Math.round(image.height * scale));
          const ctx = canvas.getContext("2d");
          ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
          resolve(canvas.toDataURL("image/jpeg", 0.82));
        };
        image.onerror = () => resolve(source);
        image.src = source;
      });
    }

    async function fileToBase64(file) {
      return dataUrlPayload(await fileToDataUrl(file));
    }

    function blobToBase64(blob) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(dataUrlPayload(reader.result));
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    }

    function dataUrlPayload(dataUrl) {
      return String(dataUrl).split(",", 2)[1] || "";
    }

    function val(id) {
      return document.getElementById(id).value.trim();
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"
      }[ch]));
    }

    syncKeyFields();
    applyAppSettings();
    if (localStorage.getItem("adminApiKey")) {
      loginWithStoredKey().then(ok => {
        if (ok) loadAll();
        else toast("Сохраненный ключ не найден на этом сервере");
      });
    } else if (key()) {
      loadAll();
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def admin_panel() -> str:
    return ADMIN_PANEL_HTML


class TextPayload(BaseModel):
    text: str = Field(min_length=1)


class AccessLoginPayload(BaseModel):
    accessKey: str = Field(min_length=1)


class UserLoginStatusPayload(BaseModel):
    loginId: str = Field(min_length=1)
    secret: str = Field(min_length=1)


class AccessKeyCreatePayload(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    userId: int


class AdminPermissionPayload(BaseModel):
    chatId: int
    userId: int
    feature: str = Field(min_length=1)
    mode: str = "write"
    allowed: bool


class MediaPayload(BaseModel):
    filename: str = Field(min_length=1)
    mimeType: str = "application/octet-stream"
    dataBase64: str = Field(min_length=1)
    caption: str | None = None
    asVoice: bool = False


class ReplyPayload(BaseModel):
    username: str = Field(min_length=1)
    text: str = Field(min_length=1)


class TriggerPayload(BaseModel):
    trigger: str = Field(min_length=1)
    text: str = Field(min_length=1)


class WordPayload(BaseModel):
    word: str = Field(min_length=1)


class AlarmPayload(BaseModel):
    enabled: bool | None = None
    alarmText: str | None = None
    clearText: str | None = None


class RollMutePayload(BaseModel):
    muteMinutes: int = Field(ge=1, le=10080)
    cooldownMinutes: int = Field(ge=0, le=10080)


class QuietPayload(BaseModel):
    replyText: str = Field(min_length=1)


class QuietManualPayload(BaseModel):
    target: str = Field(min_length=1)
    minutes: int = Field(ge=1, le=10080)
    reason: str = ""


class QuietMediaPayload(BaseModel):
    filename: str = Field(min_length=1)
    mimeType: str = "application/octet-stream"
    dataBase64: str = Field(min_length=1)
    asVoice: bool = False


class GiveawayPayload(BaseModel):
    trigger: str = Field(min_length=1)
    winnersCount: int = Field(ge=1, le=20)
    title: str = Field(min_length=1)


class BirthdayPayload(BaseModel):
    day: int = Field(ge=1, le=31)
    month: int = Field(ge=1, le=12)
    text: str = Field(min_length=1)


class AdvertisementAttachmentPayload(BaseModel):
    filename: str = Field(min_length=1)
    mimeType: str = Field(pattern=r"^(image|video)/")
    dataBase64: str = Field(min_length=1)


class AdvertisementPayload(BaseModel):
    text: str = Field(min_length=1)
    enabled: bool = True
    startMode: str = Field(pattern=r"^(now|scheduled)$")
    startTime: str = Field(pattern=r"^\d{2}:\d{2}$")
    intervalMinutes: int = Field(ge=1, le=43200)
    durationType: str = Field(pattern=r"^(once|day|unlimited)$")
    topicThreadId: int | None = None
    attachments: list[AdvertisementAttachmentPayload] = Field(default_factory=list, max_length=10)
    replaceAttachments: bool = False


class TopicTitlePayload(BaseModel):
    title: str = Field(min_length=1, max_length=128)


class DigGrantPayload(BaseModel):
    userId: int
    coins: int | None = None
    luck: int | None = Field(default=None, ge=0, le=100)
    extraDigs: int | None = None
    goldenTickets: int | None = None
    superPasses: int | None = None
    clearCooldown: bool = False


class PremiumGrantPayload(BaseModel):
    userId: int
    plan: str = Field(pattern=r"^(basic|extended)$")
    days: int = Field(default=PREMIUM_PERIOD_DAYS, ge=1, le=3660)


class MediaTaskCreatePayload(BaseModel):
    taskType: str = Field(min_length=1)
    sourceFileId: str | None = None
    sourceFilePath: str | None = None
    fileSizeBytes: int = Field(ge=0)
    durationSeconds: int | None = Field(default=None, ge=0)


class RadioRecognitionPayload(BaseModel):
    stationName: str = Field(default="", max_length=200)
    stationUuid: str = Field(min_length=8, max_length=80)


class LinkPreviewPayload(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class YoutubeDownloadPayload(BaseModel):
    user_id: int | None = Field(default=None, gt=0)
    url: str = Field(min_length=10, max_length=2048)
    download_type: str = Field(pattern=r"^(video_mp4|audio_mp3|music_mp3|music_m4a)$")


class DeviceInfoPayload(BaseModel):
    deviceId: str | None = Field(default=None, max_length=128)
    appVersion: str | None = Field(default=None, max_length=64)
    androidVersion: str | None = Field(default=None, max_length=64)
    sdk: int | None = None
    manufacturer: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    screen: str | None = Field(default=None, max_length=64)
    density: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=80)
    networkType: str | None = Field(default=None, max_length=32)


class AnalyticsPayload(BaseModel):
    app: str = Field(min_length=1, max_length=64)
    eventType: str = Field(default="event", max_length=64)
    eventName: str = Field(min_length=1, max_length=128)
    device: DeviceInfoPayload = Field(default_factory=DeviceInfoPayload)
    endpoint: str | None = Field(default=None, max_length=200)
    statusCode: int | None = None
    durationMs: int | None = None
    errorType: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


def resolve_public_stream_url(raw_url: str) -> tuple[str, str, tuple[str, ...]]:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Поток радиостанции должен быть http/https ссылкой.")
    hostname = parsed.hostname.rstrip(".").casefold()
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Некорректный порт радиопотока.") from error
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise HTTPException(status_code=422, detail="Не удалось проверить адрес радиопотока.") from error
    approved: list[str] = []
    for item in addresses:
        host = item[4][0]
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный адрес радиопотока.")
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise HTTPException(status_code=422, detail="Радиопоток ведет на запрещенный внутренний адрес.")
        normalized = str(ip)
        if normalized not in approved:
            approved.append(normalized)
    if not approved:
        raise HTTPException(status_code=422, detail="Не удалось проверить адрес радиопотока.")
    return raw_url, hostname, tuple(approved)


def require_public_stream_url(raw_url: str) -> str:
    return resolve_public_stream_url(raw_url)[0]


class PinnedPublicResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, hostname: str, addresses: tuple[str, ...]) -> None:
        self.hostname = hostname
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> list[dict[str, Any]]:
        if host.rstrip(".").casefold() != self.hostname:
            raise OSError("Unexpected hostname during pinned radio connection")
        records: list[dict[str, Any]] = []
        for address in self.addresses:
            ip = ipaddress.ip_address(address)
            address_family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, address_family}:
                continue
            records.append(
                {
                    "hostname": host,
                    "host": address,
                    "port": port,
                    "family": address_family,
                    "proto": socket.IPPROTO_TCP,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not records:
            raise OSError("No approved address for requested family")
        return records

    async def close(self) -> None:
        return None


async def download_public_stream_sample(
    raw_url: str,
    output_path: str,
    *,
    max_bytes: int = 24 * 1024 * 1024,
    max_seconds: float = 18.0,
) -> None:
    checked_url, hostname, addresses = resolve_public_stream_url(raw_url)
    connector = aiohttp.TCPConnector(
        resolver=PinnedPublicResolver(hostname, addresses),
        use_dns_cache=False,
        force_close=True,
        limit=1,
    )
    timeout = aiohttp.ClientTimeout(total=max_seconds + 5, connect=10, sock_read=8)
    started = time.monotonic()
    total = 0
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, auto_decompress=False) as session:
            async with session.get(
                checked_url,
                allow_redirects=False,
                headers={"User-Agent": "MonkeyDin/0.3", "Icy-MetaData": "0"},
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise HTTPException(status_code=502, detail="Радиопоток вернул ошибку.")
                declared_size = response.content_length
                if declared_size is not None and declared_size > max_bytes:
                    raise HTTPException(status_code=413, detail="Фрагмент радиопотока слишком большой.")
                with open(output_path, "wb") as target:
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            raise HTTPException(status_code=413, detail="Фрагмент радиопотока слишком большой.")
                        target.write(chunk)
                        if time.monotonic() - started >= max_seconds:
                            break
    except HTTPException:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
        raise HTTPException(status_code=502, detail="Не удалось безопасно получить радиопоток.") from error
    if total < 1024:
        raise HTTPException(status_code=502, detail="Радиопоток не передал достаточно данных.")


def admin_api_key() -> str:
    load_config()
    return os.getenv("ADMIN_API_KEY", "").strip()


def access_key_store_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.getenv("ADMIN_ACCESS_KEYS_FILE", os.path.join(project_root, "admin_access_keys.json")).strip()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def user_subscription_stars() -> int:
    try:
        return max(1, int(os.getenv("USER_SUBSCRIPTION_STARS", "100")))
    except ValueError:
        return 100


def user_avatar_dir() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.getenv("USER_AVATAR_DIR", os.path.join(project_root, "media_storage", "user_avatars")).strip()


def user_avatar_path(user_id: int) -> str:
    return os.path.join(user_avatar_dir(), f"{user_id}.jpg")


def avatar_signature(token_hash: str, user_id: int) -> str:
    return hash_secret(f"avatar:{token_hash}:{user_id}")


def valid_avatar_signature(user_id: int, signature: str) -> bool:
    if not signature:
        return False
    now = datetime.now(timezone.utc)
    with open_db() as db:
        sessions = db.list_user_sessions(user_id)
    for session in sessions:
        if session.revoked_at:
            continue
        try:
            if datetime.fromisoformat(session.expires_at) <= now:
                continue
        except ValueError:
            continue
        if secrets.compare_digest(avatar_signature(session.token_hash, user_id), signature):
            return True
    return False


async def ensure_user_avatar(user_id: int) -> str | None:
    path = user_avatar_path(user_id)
    max_age_seconds = 24 * 60 * 60
    if os.path.exists(path) and (datetime.now().timestamp() - os.path.getmtime(path)) < max_age_seconds:
        return path

    config = load_config()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    tmp_path = f"{path}.tmp"
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos.photos:
            return path if os.path.exists(path) else None
        sizes = photos.photos[0]
        if not sizes:
            return path if os.path.exists(path) else None
        largest = max(sizes, key=lambda item: item.file_size or 0)
        file = await bot.get_file(largest.file_id)
        if not file.file_path:
            return path if os.path.exists(path) else None
        await bot.download_file(file.file_path, destination=tmp_path)
        os.replace(tmp_path, path)
        return path
    except TelegramBadRequest:
        logging.info("User %s has no downloadable profile avatar", user_id)
        return path if os.path.exists(path) else None
    except Exception:
        logging.exception("Could not refresh profile avatar for user %s", user_id)
        return path if os.path.exists(path) else None
    finally:
        with suppress(FileNotFoundError):
            os.remove(tmp_path)
        await bot.session.close()


async def user_photo_url(request: Request, user_id: int, token_hash: str) -> str:
    avatar_path = await ensure_user_avatar(user_id)
    if not avatar_path or not os.path.exists(avatar_path):
        return ""
    signature = avatar_signature(token_hash, user_id)
    return f"{str(request.base_url).rstrip('/')}/user/avatar/{user_id}?sig={signature}"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_access_keys() -> list[dict[str, Any]]:
    path = access_key_store_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_access_keys(items: list[dict[str, Any]]) -> None:
    path = access_key_store_path()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def public_access_key(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "label": item.get("label", ""),
        "userId": item.get("userId"),
        "createdAt": item.get("createdAt"),
        "createdBy": item.get("createdBy"),
        "revokedAt": item.get("revokedAt"),
    }


def access_session(token: str) -> dict[str, Any] | None:
    item = SESSION_TOKENS.get(token)
    if not item:
        return None
    expires_at = item.get("expiresAt")
    if not isinstance(expires_at, datetime) or datetime.now(timezone.utc) >= expires_at:
        SESSION_TOKENS.pop(token, None)
        return None
    key_id = item.get("keyId")
    if key_id is not None:
        key_is_active = any(
            stored.get("id") == key_id and not stored.get("revokedAt")
            for stored in load_access_keys()
        )
        if not key_is_active:
            SESSION_TOKENS.pop(token, None)
            return None
    return item


def api_audit_action(method: str, path: str) -> str:
    if "/triggers" in path:
        return "Удалил триггер" if method == "DELETE" else "Добавил или изменил триггер"
    if "/replies" in path:
        return "Удалил @ответ" if method == "DELETE" else "Добавил или изменил @ответ"
    if "/quotes" in path:
        return "Удалил цитату" if method == "DELETE" else "Добавил цитату"
    labels = [
        ("advertisements", "Изменил рекламу"),
        ("topics", "Переименовал тему"),
        ("blacklist", "Изменил черный список"),
        ("birthdays", "Изменил дни рождения"),
        ("quiet", "Изменил настройки «Затихни»"),
        ("roll-mute", "Изменил Roll mute"),
        ("giveaway", "Изменил розыгрыш"),
        ("dig/grant", "Изменил ресурсы шахты"),
        ("premium/grant", "Выдал Premium"),
        ("/message", "Отправил сообщение через панель"),
        ("/media", "Отправил медиа через панель"),
        ("feedback", "Отправил обратную связь"),
        ("permissions", "Изменил права доступа"),
        ("access-keys", "Изменил ключи доступа"),
        ("restart", "Перезапустил панель"),
    ]
    for fragment, label in labels:
        if fragment in path:
            return label
    return f"{method} в панели"


@app.middleware("http")
async def audit_api_request(request: Request, call_next):
    chat_match = re.search(r"/admin/chats/(-?\d+)", request.url.path)
    chat_id = int(chat_match.group(1)) if chat_match else None
    chat_token = CURRENT_ADMIN_CHAT_ID.set(chat_id)
    try:
        response = await call_next(request)
    finally:
        CURRENT_ADMIN_CHAT_ID.reset(chat_token)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; media-src 'self' blob: https: http:; connect-src 'self' https:; "
        "object-src 'none'; frame-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    )
    if request.url.path.startswith(("/admin", "/user", "/premium", "/media", "/youtube")):
        response.headers.setdefault("Cache-Control", "no-store")
    if request.url.path.startswith("/user/"):
        return response
    if request.method not in {"POST", "PUT", "DELETE"} or response.status_code >= 400:
        return response
    if request.url.path in {"/admin/auth/login"}:
        return response
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    actor_id = None
    actor_name = "ключ приложения"
    if token and secrets.compare_digest(token, admin_api_key()):
        actor_id = admin_actor_id()
        actor_name = "владелец"
    else:
        session = access_session(token)
        if session:
            actor_id = int(session["userId"])
            actor_name = str(session.get("label", "ключ приложения"))
    action = api_audit_action(request.method, request.url.path)
    chat_title = None
    try:
        with open_db() as db:
            chat = db.get_chat(chat_id) if chat_id is not None else None
            chat_title = chat.title if chat else None
            db.add_audit_log(
                "приложение",
                action,
                chat_id=chat_id,
                actor_id=actor_id,
                actor_name=actor_name,
                details=request.url.path,
            )
    except Exception:
        logging.exception("Could not save API audit action")
    is_chat_send = re.fullmatch(r"/admin/chats/-?\d+/(message|media)", request.url.path) is not None
    if not is_chat_send:
        await notify_staff_api_audit(actor_name, action, chat_title, request.url.path)
    return response


async def live_chat_admin(user_id: int, chat_id: int) -> bool:
    cache_key = (chat_id, user_id)
    now = asyncio.get_running_loop().time()
    cached = ADMIN_MEMBERSHIP_CACHE.get(cache_key)
    # Positive authorization decisions are never cached: a Telegram admin may
    # be removed at any moment. Short negative caching only limits abuse.
    if cached and cached[0] > now and not cached[1]:
        return False
    config = load_config()
    bot = Bot(token=config.bot_token)
    allowed = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        status = getattr(member.status, "value", member.status)
        allowed = status in {"administrator", "creator"}
    except (TelegramBadRequest, TelegramForbiddenError):
        allowed = False
    finally:
        await bot.session.close()
    if allowed:
        ADMIN_MEMBERSHIP_CACHE.pop(cache_key, None)
    else:
        ADMIN_MEMBERSHIP_CACHE[cache_key] = (now + ADMIN_MEMBERSHIP_CACHE_SECONDS, False)
    return allowed


async def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    key = admin_api_key()
    if not key:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY is not set in .env")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    token = authorization.removeprefix("Bearer ").strip()
    if secrets.compare_digest(token, key):
        CURRENT_ADMIN_ACTOR_ID.set(admin_actor_id())
        return
    session = access_session(token)
    if session:
        actor_id = int(session["userId"])
        chat_id = CURRENT_ADMIN_CHAT_ID.get()
        config = load_config()
        if actor_id not in config.bot_admin_ids and actor_id != config.owner_id:
            if chat_id is not None and not await live_chat_admin(actor_id, chat_id):
                raise HTTPException(status_code=403, detail="Права администратора этой группы больше не действуют.")
        CURRENT_ADMIN_ACTOR_ID.set(actor_id)
        return
    raise HTTPException(status_code=401, detail="Invalid admin API key")


async def require_user(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid user token")
    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token.startswith(USER_SESSION_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid user token")
    with open_db() as db:
        session = db.get_user_session(hash_secret(raw_token))
    if not session or session.revoked_at or datetime.fromisoformat(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="User session expired")
    return {
        "userId": session.user_id,
        "username": session.username,
        "fullName": session.full_name,
        "tokenHash": session.token_hash,
    }


@contextmanager
def open_db():
    config = load_config()
    db = Database(config.db_path)
    db.init()
    try:
        yield db
    finally:
        db.close()


def dump(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [dump(item) for item in value]
    return value


def dump_advertisements(db: Database, chat_id: int) -> list[dict[str, Any]]:
    return [
        {
            **dump(advertisement),
            "attachments": dump(db.list_advertisement_attachments(advertisement.id)),
        }
        for advertisement in db.list_advertisements(chat_id)
    ]


def ok(message: str = "ok") -> dict[str, Any]:
    return {"ok": True, "message": message}


def save_analytics_event(db: Database, payload: AnalyticsPayload, user_id: int | None) -> int:
    device = payload.device
    return db.add_device_event(
        app=payload.app,
        event_type=payload.eventType,
        event_name=payload.eventName,
        user_id=user_id,
        device_id=device.deviceId,
        app_version=device.appVersion,
        android_version=device.androidVersion,
        sdk=device.sdk,
        manufacturer=device.manufacturer,
        model=device.model,
        screen=device.screen,
        density=device.density,
        locale=device.locale,
        timezone=device.timezone,
        network_type=device.networkType,
        endpoint=payload.endpoint,
        status_code=payload.statusCode,
        duration_ms=payload.durationMs,
        error_type=payload.errorType,
        message=payload.message,
        metadata=payload.metadata,
    )


def require_chat(db: Database, chat_id: int) -> None:
    if not db.get_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    if owner_actions_allowed():
        return
    actor_id = current_actor_id()
    if actor_id is None or chat_id not in db.user_admin_chat_ids(actor_id):
        raise HTTPException(status_code=403, detail="This key has no access to this chat")


def render_quiet_reply(template: str | None, target_name: str, minutes: int, reason: str) -> str:
    text = template or "{user} затих на <b>{minutes}</b> мин.{reason_line}"
    reason_line = f"\nПричина: {escape(reason)}" if reason else ""
    return (
        text.replace("{user}", escape(target_name))
        .replace("{minutes}", str(minutes))
        .replace("{reason}", escape(reason))
        .replace("{reason_line}", reason_line)
    )


def participant_since_date(period: str) -> str | None:
    today = datetime.now(timezone.utc).date()
    if period == "day":
        return today.isoformat()
    if period == "week":
        return (today - timedelta(days=6)).isoformat()
    if period == "month":
        return (today - timedelta(days=29)).isoformat()
    if period == "all":
        return None
    raise HTTPException(status_code=400, detail="Unknown period")


def advertisement_scheduled_at(payload: AdvertisementPayload) -> str:
    hour, minute = [int(part) for part in payload.startTime.split(":", 1)]
    if hour > 23 or minute > 59:
        raise HTTPException(status_code=400, detail="Invalid advertisement start time")
    now = datetime.now().astimezone()
    if payload.startMode == "now":
        return now.isoformat(timespec="seconds")
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return scheduled.isoformat(timespec="seconds")


async def resolve_quiet_target(bot: Bot, db: Database, chat_id: int, target: str) -> tuple[int, str]:
    target = target.strip()
    if target.lstrip("-").isdigit():
        user_id = int(target)
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            raise HTTPException(status_code=400, detail=f"User not found in chat: {exc}") from exc
        user = member.user
        db.upsert_seen_user(chat_id, user.id, user.username, user.full_name, user.is_bot)
        return user.id, f"@{user.username}" if user.username else user.full_name

    username = normalize_username(target)
    user = db.get_seen_user_by_username(chat_id, username)
    if not user:
        raise HTTPException(status_code=404, detail="User was not seen in this chat yet")
    return user.user_id, f"@{user.username}" if user.username else user.full_name


async def send_saved_quiet_media(
    bot: Bot,
    chat_id: int,
    media_type: str | None,
    file_id: str | None,
    reply_to_message_id: int | None = None,
) -> None:
    if not media_type or not file_id:
        return
    if media_type == "animation":
        await bot.send_animation(chat_id, file_id, reply_to_message_id=reply_to_message_id)
    elif media_type == "voice":
        await bot.send_voice(chat_id, file_id, reply_to_message_id=reply_to_message_id)
    elif media_type == "audio":
        await bot.send_audio(chat_id, file_id, reply_to_message_id=reply_to_message_id)


@app.get("/premium/plans")
def premium_plans() -> dict[str, Any]:
    return {"items": [plan_public_dict(plan) for plan in PLANS.values()]}


@app.get("/premium/me")
def premium_me(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    config = load_config()
    premium = PremiumService(config.db_path)
    try:
        user_id = int(user["userId"])
        plan = premium.get_user_plan(user_id)
        subscription = premium.get_user_subscription(user_id)
        return {
            "active": plan is not None,
            "plan": plan_public_dict(plan) if plan else None,
            "subscription": dict(subscription) if subscription else None,
            "usageToday": premium.daily_media_usage(user_id),
        }
    finally:
        premium.close()


@app.get("/user/premium/plans")
def user_premium_plans(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    return {"items": [plan_public_dict(plan) for plan in PLANS.values()]}


@app.get("/user/premium/me")
def user_premium_me(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    premium = PremiumService(load_config().db_path)
    try:
        user_id = int(user["userId"])
        plan = premium.get_user_plan(user_id)
        subscription = premium.get_user_subscription(user_id)
        return {
            "active": plan is not None,
            "plan": plan_public_dict(plan) if plan else None,
            "subscription": dict(subscription) if subscription else None,
            "usageToday": premium.daily_media_usage(user_id),
        }
    finally:
        premium.close()


@app.post("/user/premium/invoice/{plan_key}")
async def user_premium_invoice(plan_key: str, user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    plan = PLANS.get(plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Premium plan not found")
    config = load_config()
    payload = f"premium_plan:{plan.key}:{int(user['userId'])}:{secrets.token_hex(8)}"
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        url = await bot.create_invoice_link(
            title=plan.title,
            description="Premium на 30 дней: медиа-функции и бонусы шахты.",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=plan.title, amount=plan.price_stars)],
            provider_token="",
        )
    finally:
        await bot.session.close()
    return {"invoiceUrl": url, "plan": plan_public_dict(plan), "periodDays": 30}


@app.post("/user/premium/test")
def user_premium_test(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    config = load_config()
    user_id = int(user["userId"])
    if config.owner_id is None or user_id != config.owner_id:
        raise HTTPException(status_code=403, detail="Тест Premium доступен только владельцу бота.")
    premium = PremiumService(config.db_path)
    try:
        current_plan = premium.get_user_plan(user_id)
        if current_plan is not None:
            current = premium.get_user_subscription(user_id)
            return {"ok": True, "alreadyActive": True, "subscription": dict(current) if current else None}
        subscription = premium.activate_subscription(
            user_id=user_id,
            username=user.get("username"),
            plan="extended",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            telegram_payment_charge_id=None,
        )
        premium.log("INFO", f"Owner Premium test activated: user={user_id}")
        return {"ok": True, "subscription": dict(subscription)}
    finally:
        premium.close()


@app.post("/media/tasks")
async def create_media_task(
    payload: MediaTaskCreatePayload,
    user: Annotated[dict[str, Any], Depends(require_user)],
) -> dict[str, Any]:
    config = load_config()
    media = MediaTaskService(config.db_path)
    user_id = int(user["userId"])
    if payload.taskType in {
        "youtube_video", "youtube_audio", "youtube_music_audio",
        "instagram_video", "instagram_audio",
    }:
        raise HTTPException(
            status_code=400,
            detail="Сетевые загрузки создаются только через /youtube/download с проверкой URL и размера.",
        )
    try:
        task = media.create_media_task(
            user_id=user_id,
            task_type=payload.taskType,
            source_file_id=payload.sourceFileId,
            source_file_path=payload.sourceFilePath,
            file_size_bytes=payload.fileSizeBytes,
            duration_seconds=payload.durationSeconds,
        )
        return dump(task)
    except PremiumRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PremiumLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (PremiumError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.exception("Media task creation failed")
        await notify_staff_critical(f"Ошибка создания media_task для user={user_id}: {exc!r}")
        raise HTTPException(status_code=500, detail="Не получилось создать медиа-задачу.") from exc
    finally:
        media.close()


@app.post("/youtube/download")
async def youtube_download_task(
    payload: YoutubeDownloadPayload,
    user: Annotated[dict[str, Any], Depends(require_user)],
) -> dict[str, Any]:
    user_id = int(user["userId"])
    if payload.user_id is not None and int(payload.user_id) != user_id:
        raise HTTPException(status_code=403, detail="user_id does not match current user session")
    if payload.download_type not in DOWNLOAD_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported download_type")
    media = MediaTaskService(load_config().db_path)
    try:
        info = await asyncio.to_thread(inspect_youtube, payload.url, payload.download_type)
        if payload.download_type.startswith("music_") and not info.is_music:
            raise YoutubeMediaError("Форматы YouTube Music доступны только для ссылок music.youtube.com.")
        task_type = {
            "video_mp4": "youtube_video",
            "audio_mp3": "youtube_audio",
            "music_mp3": "youtube_music_audio",
            "music_m4a": "youtube_music_audio",
        }[payload.download_type]
        task = media.create_media_task(
            user_id=user_id,
            task_type=task_type,
            source_file_id=payload.download_type,
            source_file_path=payload.url,
            file_size_bytes=info.estimated_size,
            duration_seconds=info.duration,
        )
        media.premium.log("INFO", f"YouTube API task created: id={task.id}, user={user_id}, type={payload.download_type}")
        return {"task": dump(task), "title": info.title, "estimatedSizeBytes": info.estimated_size}
    except PremiumRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PremiumLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YoutubeMediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.exception("YouTube task creation failed")
        await notify_staff_critical(f"Ошибка создания YouTube-задачи для user={user_id}: {exc!r}")
        raise HTTPException(status_code=500, detail="Не получилось создать YouTube-задачу.") from exc
    finally:
        media.close()


@app.get("/media/tasks")
def media_tasks(
    user: Annotated[dict[str, Any], Depends(require_user)],
    limit: int = 20,
) -> dict[str, Any]:
    media = MediaTaskService(load_config().db_path)
    try:
        user_id = int(user["userId"])
        return {"items": dump(media.get_user_media_tasks(user_id, limit))}
    finally:
        media.close()


@app.get("/media/tasks/{task_id}")
def media_task(task_id: int, user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    media = MediaTaskService(load_config().db_path)
    try:
        user_id = int(user["userId"])
        task = media.get_media_task(task_id)
        if not task or task.user_id != user_id:
            raise HTTPException(status_code=404, detail="Media task not found")
        return dump(task)
    finally:
        media.close()


@app.post("/user/auth/start")
async def user_auth_start() -> dict[str, Any]:
    login_id = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=USER_LOGIN_TTL_MINUTES)
    with open_db() as db:
        db.create_user_login_request(login_id, hash_secret(secret), expires_at.isoformat(timespec="seconds"))
    config = load_config()
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
    finally:
        await bot.session.close()
    return {
        "loginId": login_id,
        "secret": secret,
        "botUrl": f"https://t.me/{me.username}?start=app_{login_id}",
        "expiresAt": expires_at.isoformat(timespec="seconds"),
    }


@app.post("/user/auth/status")
def user_auth_status(payload: UserLoginStatusPayload) -> dict[str, Any]:
    with open_db() as db:
        request = db.get_user_login_request(payload.loginId)
        if not request or not secrets.compare_digest(request.secret_hash, hash_secret(payload.secret)):
            raise HTTPException(status_code=404, detail="Login request not found")
        if datetime.fromisoformat(request.expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Login request expired")
        if request.consumed_at:
            raise HTTPException(status_code=410, detail="Login request already used")
        if not request.approved_at or request.user_id is None:
            return {"status": "pending"}
        raw_token = USER_SESSION_PREFIX + secrets.token_urlsafe(36)
        expires_at = datetime.now(timezone.utc) + timedelta(days=USER_SESSION_DAYS)
        consumed = db.consume_user_login_and_create_session(
            request.login_id,
            hash_secret(payload.secret),
            hash_secret(raw_token),
            request.user_id,
            request.username,
            request.full_name or str(request.user_id),
            expires_at.isoformat(timespec="seconds"),
        )
        if not consumed:
            raise HTTPException(status_code=410, detail="Login request already used")
        return {
            "status": "approved",
            "userToken": raw_token,
            "expiresAt": expires_at.isoformat(timespec="seconds"),
        }


@app.get("/user/me")
async def user_me(request: Request, user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    user_id = int(user["userId"])
    with open_db() as db:
        subscription = db.get_user_subscription(user_id)
    config = load_config()
    premium = PremiumService(config.db_path)
    try:
        premium_plan = premium.get_user_plan(user_id)
        premium_subscription = premium.get_user_subscription(user_id)
        premium_data = {
            "active": premium_plan is not None,
            "plan": plan_public_dict(premium_plan) if premium_plan else None,
            "subscription": dict(premium_subscription) if premium_subscription else None,
            "usageToday": premium.daily_media_usage(user_id),
            "radioRecognitionsToday": premium.daily_radio_recognition_usage(user_id),
        }
    finally:
        premium.close()
    active = (
        subscription.status == "active"
        and subscription.expires_at is not None
        and datetime.fromisoformat(subscription.expires_at) > datetime.now(timezone.utc)
    )
    photo_url = await user_photo_url(request, user_id, str(user["tokenHash"]))
    return {
        "userId": user_id,
        "username": user["username"],
        "fullName": user["fullName"],
        "photoUrl": photo_url,
        "isOwner": config.owner_id is not None and user_id == config.owner_id,
        "premium": premium_data,
        "subscription": {
            "active": active,
            "status": subscription.status,
            "expiresAt": subscription.expires_at,
        },
    }


@app.get("/user/profile")
async def user_profile(request: Request, user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    user_id = int(user["userId"])
    config = load_config()
    premium = PremiumService(config.db_path)
    try:
        with open_db() as db:
            photo_url = await user_photo_url(request, user_id, str(user["tokenHash"]))
            return build_user_profile(
                db,
                premium,
                user_id,
                user.get("username"),
                str(user.get("fullName") or user_id),
                photo_url=photo_url,
            )
    finally:
        premium.close()


@app.get("/user/avatar/{user_id}")
def user_avatar(user_id: int, sig: str = "") -> FileResponse:
    if not valid_avatar_signature(user_id, sig):
        raise HTTPException(status_code=403, detail="Avatar link is invalid or expired")
    path = user_avatar_path(user_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(path, media_type="image/jpeg", filename=f"user_{user_id}.jpg")


@app.post("/user/analytics")
def user_analytics(payload: AnalyticsPayload, user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    with open_db() as db:
        event_id = save_analytics_event(db, payload, int(user["userId"]))
    return {"ok": True, "id": event_id}


@app.post("/user/radio/recognize")
async def user_radio_recognize(
    payload: RadioRecognitionPayload,
    user: Annotated[dict[str, Any], Depends(require_user)],
) -> dict[str, Any]:
    token = os.getenv("AUDD_API_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="Распознавание треков пока не настроено.")
    premium = PremiumService(load_config().db_path)
    user_id = int(user["userId"])
    slot_claimed = False
    try:
        try:
            plan = premium.claim_radio_recognition_slot(user_id)
            slot_claimed = True
        except PremiumRequiredError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except PremiumLimitError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error

        timeout = aiohttp.ClientTimeout(total=40)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://de1.api.radio-browser.info/json/stations/byuuid/{payload.stationUuid}",
                headers={"User-Agent": "MonkeyDin/0.3"},
            ) as station_response:
                stations = await station_response.json(content_type=None)
            if not stations:
                raise HTTPException(status_code=404, detail="Радиостанция больше не найдена.")
            station_url = stations[0].get("url_resolved") or stations[0].get("url")
            if not station_url:
                raise HTTPException(status_code=422, detail="У станции нет рабочего потока.")
            with tempfile.TemporaryDirectory(prefix="monkeydin-radio-") as temp_dir:
                stream_path = os.path.join(temp_dir, "stream-source")
                sample_path = os.path.join(temp_dir, "sample.mp3")
                await download_public_stream_sample(str(station_url), stream_path)
                command = [
                    find_ffmpeg(),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    stream_path,
                    "-t",
                    "15",
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    sample_path,
                ]
                try:
                    await asyncio.to_thread(subprocess.run, command, check=True, timeout=30)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
                    raise HTTPException(status_code=502, detail="Не удалось записать 15 секунд эфира через FFmpeg.") from error
                with open(sample_path, "rb") as sample_file:
                    audio = sample_file.read()
            form = aiohttp.FormData()
            form.add_field("api_token", token)
            form.add_field("return", "apple_music,spotify")
            form.add_field("file", audio, filename="radio-sample.mp3", content_type="audio/mpeg")
            async with session.post("https://api.audd.io/", data=form) as response:
                result = await response.json(content_type=None)
        if result.get("status") != "success":
            raise HTTPException(status_code=502, detail="Сервис распознавания временно недоступен.")
        track = result.get("result")
        if not track:
            return {
                "found": False,
                "usageToday": premium.daily_radio_recognition_usage(user_id),
                "limit": plan.daily_radio_recognitions,
            }
        spotify = track.get("spotify") or {}
        apple = track.get("apple_music") or {}
        images = (spotify.get("album") or {}).get("images") or []
        artwork = images[0].get("url") if images else (apple.get("artwork") or {}).get("url")
        item = {
            "artist": track.get("artist") or "Неизвестный исполнитель",
            "title": track.get("title") or "Неизвестный трек",
            "album": track.get("album"),
            "artworkUrl": artwork,
        }
        if plan.radio_track_history:
            premium.add_radio_track(
                user_id,
                payload.stationName.strip(),
                item["artist"],
                item["title"],
                item["album"],
                item["artworkUrl"],
            )
        return {
            "found": True,
            "track": item,
            "savedToHistory": plan.radio_track_history,
            "usageToday": premium.daily_radio_recognition_usage(user_id),
            "limit": plan.daily_radio_recognitions,
        }
    except Exception:
        if slot_claimed:
            premium.release_radio_recognition_slot(user_id)
        raise
    finally:
        premium.close()


@app.get("/user/radio/history")
def user_radio_history(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    premium = PremiumService(load_config().db_path)
    try:
        plan = premium.get_user_plan(int(user["userId"]))
        if plan is None or not plan.radio_track_history:
            raise HTTPException(status_code=403, detail="История треков доступна в Расширенном Premium.")
        return {"items": [dict(row) for row in premium.radio_track_history(int(user["userId"]))]}
    finally:
        premium.close()


@app.post("/user/link/preview")
async def user_link_preview(
    payload: LinkPreviewPayload,
    user: Annotated[dict[str, Any], Depends(require_user)],
) -> dict[str, Any]:
    premium = PremiumService(load_config().db_path)
    try:
        if premium.get_user_plan(int(user["userId"])) is None:
            raise HTTPException(status_code=403, detail="Для работы со ссылками нужен Premium.")
    finally:
        premium.close()
    url = payload.url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Поддерживаются только http/https ссылки.")
    if host in {"open.spotify.com", "spotify.com", "www.spotify.com"}:
        return await preview_spotify_link(url)
    if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}:
        return await preview_soundcloud_link(url)
    if host in {"instagram.com", "www.instagram.com"}:
        return {
            "platform": "instagram",
            "title": "Instagram Reels",
            "artist": "",
            "album": "",
            "artworkUrl": "",
            "durationMs": 0,
            "sourceUrl": url,
            "note": "Instagram не дает легального публичного API для скачивания Reels по чужой ссылке. Сохраняю карточку и ссылку.",
        }
    raise HTTPException(status_code=400, detail="Пока поддерживаются Spotify, SoundCloud и Instagram ссылки.")


async def preview_spotify_link(url: str) -> dict[str, Any]:
    load_config()
    match = re.search(r"open\.spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)", url)
    if not match:
        raise HTTPException(status_code=400, detail="Не удалось распознать Spotify ссылку.")
    item_type, item_id = match.group(1), match.group(2)
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return await preview_spotify_public_link(url, item_type)
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            auth = aiohttp.BasicAuth(client_id, client_secret)
            async with session.post("https://accounts.spotify.com/api/token", auth=auth, data={"grant_type": "client_credentials"}) as token_response:
                if token_response.status >= 400:
                    return await preview_spotify_public_link(url, item_type)
                token = (await token_response.json()).get("access_token")
            async with session.get(f"https://api.spotify.com/v1/{item_type}s/{item_id}", headers={"Authorization": f"Bearer {token}"}) as response:
                if response.status >= 400:
                    return await preview_spotify_public_link(url, item_type)
                data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return await preview_spotify_public_link(url, item_type)
    if item_type == "track":
        album = data.get("album") or {}
        images = album.get("images") or []
        return {
            "platform": "spotify",
            "type": "track",
            "title": data.get("name") or "Spotify track",
            "artist": ", ".join(artist.get("name", "") for artist in data.get("artists", [])),
            "album": album.get("name") or "",
            "artworkUrl": images[0].get("url") if images else "",
            "durationMs": int(data.get("duration_ms") or 0),
            "sourceUrl": url,
            "note": "Spotify API дает метаданные, но не аудиофайл для скачивания.",
        }
    images = data.get("images") or []
    return {
        "platform": "spotify",
        "type": item_type,
        "title": data.get("name") or "Spotify",
        "artist": data.get("owner", {}).get("display_name", "") if item_type == "playlist" else ", ".join(a.get("name", "") for a in data.get("artists", [])),
        "album": "",
        "artworkUrl": images[0].get("url") if images else "",
        "durationMs": 0,
        "sourceUrl": url,
        "note": "Можно добавить в коллекцию и искать аналоги на YouTube/YouTube Music.",
    }


async def preview_spotify_public_link(url: str, item_type: str) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=20)
    title = "Spotify ссылка"
    artist = ""
    artwork = ""
    async with aiohttp.ClientSession(timeout=timeout) as session:
        with suppress(aiohttp.ClientError, asyncio.TimeoutError):
            async with session.get("https://open.spotify.com/oembed", params={"url": url}) as response:
                if response.status < 400:
                    data = await response.json(content_type=None)
                    title = data.get("title") or title
                    artwork = data.get("thumbnail_url") or artwork
        with suppress(aiohttp.ClientError, asyncio.TimeoutError):
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=False) as response:
                if response.status < 400:
                    page = await response.text()
                    page_title = extract_html_title(page)
                    if page_title:
                        parsed_title, parsed_artist = parse_spotify_page_title(page_title)
                        title = parsed_title or title
                        artist = parsed_artist or artist
                    artwork = extract_meta_content(page, "og:image") or artwork
    return {
        "platform": "spotify",
        "type": item_type,
        "title": title,
        "artist": artist,
        "album": "",
        "artworkUrl": artwork,
        "durationMs": 0,
        "sourceUrl": url,
        "note": "Карточка получена через публичные метаданные Spotify. Длительность и альбом могут быть недоступны без Spotify Web API.",
    }


def extract_html_title(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(1)).strip())


def extract_meta_content(page: str, property_name: str) -> str:
    pattern = rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, page, re.I)
    return unescape(match.group(1)).strip() if match else ""


def parse_spotify_page_title(page_title: str) -> tuple[str, str]:
    title = page_title.replace("| Spotify", "").strip()
    artist = ""
    match = re.match(r"(.+?)\s+-\s+(?:song and lyrics by|песня и слова)\s+(.+)$", title, re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.match(r"(.+?)\s+-\s+(.+)$", title)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return title, artist


async def preview_soundcloud_link(url: str) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get("https://soundcloud.com/oembed", params={"format": "json", "url": url}) as response:
            if response.status >= 400:
                raise HTTPException(status_code=502, detail="SoundCloud не вернул данные ссылки.")
            data = await response.json(content_type=None)
    title = data.get("title") or "SoundCloud"
    author = data.get("author_name") or ""
    return {
        "platform": "soundcloud",
        "type": "track",
        "title": title,
        "artist": author,
        "album": "",
        "artworkUrl": data.get("thumbnail_url") or "",
        "durationMs": 0,
        "sourceUrl": url,
        "note": "Показываю карточку SoundCloud. Скачивание доступно только если правообладатель разрешил его на стороне SoundCloud.",
    }


@app.post("/user/auth/logout")
def user_logout(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    with open_db() as db:
        db.revoke_user_session(str(user["tokenHash"]))
    return ok("logged out")


@app.post("/user/subscription/invoice")
async def user_subscription_invoice(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    config = load_config()
    payload = f"user_subscription:{int(user['userId'])}:{secrets.token_hex(8)}"
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        url = await bot.create_invoice_link(
            title="Подписка MonkeyDin",
            description="Доступ к платным функциям MonkeyDin на 30 дней.",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label="Подписка на 30 дней", amount=user_subscription_stars())],
            provider_token="",
            subscription_period=USER_SUBSCRIPTION_PERIOD,
        )
    finally:
        await bot.session.close()
    return {"invoiceUrl": url, "stars": user_subscription_stars(), "periodDays": 30}


@app.post("/admin/auth/login")
def auth_login(payload: AccessLoginPayload) -> dict[str, Any]:
    raw_key = payload.accessKey.strip()
    master_key = admin_api_key()
    config = load_config()
    actor_id: int | None = None
    label = "master"
    key_id: str | None = None
    if master_key and secrets.compare_digest(raw_key, master_key):
        actor_id = admin_actor_id()
        if actor_id is None and len(config.bot_admin_ids) == 1:
            actor_id = next(iter(config.bot_admin_ids))
    else:
        key_hash = hash_secret(raw_key)
        for item in load_access_keys():
            if item.get("revokedAt"):
                continue
            if secrets.compare_digest(str(item.get("keyHash", "")), key_hash):
                actor_id = int(item["userId"])
                label = str(item.get("label", "access key"))
                key_id = str(item.get("id", "")) or None
                break
    if actor_id is None:
        raise HTTPException(status_code=401, detail="Invalid access key")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ACCESS_SESSION_HOURS)
    SESSION_TOKENS[token] = {"userId": actor_id, "label": label, "keyId": key_id, "expiresAt": expires_at}
    return {
        "ok": True,
        "sessionToken": token,
        "userId": actor_id,
        "label": label,
        "expiresAt": expires_at.isoformat(timespec="seconds"),
    }


@app.get("/admin/access-keys", dependencies=[Depends(require_admin)])
def list_access_keys() -> list[dict[str, Any]]:
    require_owner_action()
    return [public_access_key(item) for item in load_access_keys()]


@app.post("/admin/access-keys", dependencies=[Depends(require_admin)])
def create_access_key(payload: AccessKeyCreatePayload) -> dict[str, Any]:
    require_owner_action()
    raw_key = ACCESS_KEY_PREFIX + secrets.token_urlsafe(24)
    item = {
        "id": secrets.token_hex(8),
        "label": payload.label.strip(),
        "userId": payload.userId,
        "keyHash": hash_secret(raw_key),
        "createdAt": utc_iso(),
        "createdBy": current_actor_id(),
        "revokedAt": None,
    }
    items = load_access_keys()
    items.append(item)
    save_access_keys(items)
    return {**public_access_key(item), "accessKey": raw_key}


@app.delete("/admin/access-keys/inactive", dependencies=[Depends(require_admin)])
def delete_inactive_access_keys() -> dict[str, Any]:
    require_owner_action()
    items = load_access_keys()
    active_items = [item for item in items if not item.get("revokedAt")]
    deleted = len(items) - len(active_items)
    if deleted:
        save_access_keys(active_items)
    return {"ok": True, "deleted": deleted}


@app.delete("/admin/access-keys/{key_id}", dependencies=[Depends(require_admin)])
def revoke_access_key(key_id: str) -> dict[str, Any]:
    require_owner_action()
    items = load_access_keys()
    changed = False
    for item in items:
        if item.get("id") == key_id and not item.get("revokedAt"):
            item["revokedAt"] = utc_iso()
            changed = True
            break
    if changed:
        save_access_keys(items)
        for token, session in list(SESSION_TOKENS.items()):
            if session.get("keyId") == key_id:
                SESSION_TOKENS.pop(token, None)
    return ok("revoked" if changed else "not found")


@app.get("/admin/permissions", dependencies=[Depends(require_admin)])
def list_admin_permissions(chatId: int) -> dict[str, Any]:
    require_owner_action()
    with open_db() as db:
        require_chat(db, chatId)
        permissions = dump(db.list_admin_feature_permissions(chatId))
    return {"features": ADMIN_FEATURES, "subFeatures": ADMIN_SUBFEATURES, "permissions": permissions}


@app.post("/admin/permissions", dependencies=[Depends(require_admin)])
def set_admin_permission(payload: AdminPermissionPayload) -> dict[str, Any]:
    require_owner_action()
    if payload.feature not in ADMIN_PERMISSION_IDS:
        raise HTTPException(status_code=400, detail="Unknown admin permission")
    if payload.mode not in {"view", "write"}:
        raise HTTPException(status_code=400, detail="Unknown permission mode")
    with open_db() as db:
        require_chat(db, payload.chatId)
        db.set_admin_feature_permission(
            payload.chatId,
            payload.userId,
            permission_key(payload.feature, payload.mode),
            payload.allowed,
            current_actor_id(),
        )
        if "." not in payload.feature:
            db.set_admin_feature_permission(payload.chatId, payload.userId, payload.feature, False, current_actor_id())
    return ok("permission updated")


def admin_actor_id() -> int | None:
    raw = os.getenv("ADMIN_ACTOR_ID", "").strip()
    return int(raw) if raw else None


def owner_actions_allowed() -> bool:
    config = load_config()
    actor_id = current_actor_id()
    return actor_id is not None and actor_id in config.bot_admin_ids


def require_owner_action() -> None:
    if not owner_actions_allowed():
        raise HTTPException(status_code=403, detail="Only bot owner admins can do this")


def require_owner_only() -> None:
    config = load_config()
    if config.owner_id is None or current_actor_id() != config.owner_id:
        raise HTTPException(status_code=403, detail="Только владелец бота может выдавать билеты.")


def current_actor_id() -> int | None:
    return CURRENT_ADMIN_ACTOR_ID.get()


def permission_key(feature: str, mode: str) -> str:
    normalized_mode = mode if mode in {"view", "write"} else "write"
    return f"{feature}.{normalized_mode}"


def admin_feature_allowed(db: Database, feature: str, mode: str = "write", chat_id: int | None = None) -> bool:
    if owner_actions_allowed():
        return True
    actor_id = current_actor_id()
    scoped_chat_id = chat_id if chat_id is not None else CURRENT_ADMIN_CHAT_ID.get()
    if actor_id is None or scoped_chat_id is None:
        return False
    mode_value = db.admin_feature_permission(scoped_chat_id, actor_id, permission_key(feature, mode))
    if mode_value is not None:
        return mode_value
    if db.has_admin_feature_permission(scoped_chat_id, actor_id, permission_key(feature, "view")) or db.has_admin_feature_permission(
        scoped_chat_id, actor_id, permission_key(feature, "write")
    ):
        return False
    legacy_value = db.admin_feature_permission(scoped_chat_id, actor_id, feature)
    if legacy_value is not None:
        return legacy_value
    if "." not in feature:
        return False
    parent = feature.split(".", 1)[0]
    parent_mode_value = db.admin_feature_permission(scoped_chat_id, actor_id, permission_key(parent, mode))
    if parent_mode_value is not None:
        return parent_mode_value
    if db.has_admin_feature_permission(scoped_chat_id, actor_id, permission_key(parent, "view")) or db.has_admin_feature_permission(
        scoped_chat_id, actor_id, permission_key(parent, "write")
    ):
        return False
    return db.admin_feature_allowed(scoped_chat_id, actor_id, parent, default=False)


def require_admin_feature(db: Database, feature: str, mode: str = "write") -> None:
    if feature not in ADMIN_PERMISSION_IDS:
        raise HTTPException(status_code=400, detail="Unknown admin permission")
    if not admin_feature_allowed(db, feature, mode=mode):
        raise HTTPException(status_code=403, detail="This admin feature is not allowed")


def feature_permissions_for_actor(db: Database, chat_id: int | None = None) -> dict[str, bool]:
    return {item["id"]: feature_permission_modes_for_actor(db, chat_id)[item["id"]]["view"] for item in ADMIN_FEATURES}


def feature_permission_modes_for_actor(db: Database, chat_id: int | None = None) -> dict[str, dict[str, bool]]:
    if owner_actions_allowed():
        return {feature_id: {"view": True, "write": True} for feature_id in ADMIN_PERMISSION_IDS}
    actor_id = current_actor_id()
    items = list(ADMIN_FEATURE_IDS) + [item["id"] for children in ADMIN_SUBFEATURES.values() for item in children]
    return {
        item["id"]: {
            "view": admin_feature_allowed(db, item["id"], mode="view", chat_id=chat_id),
            "write": admin_feature_allowed(db, item["id"], mode="write", chat_id=chat_id),
        }
        for item in [{"id": feature_id} for feature_id in items]
    }


async def restart_admin_api(delay_seconds: float = 1.0) -> None:
    await asyncio.sleep(delay_seconds)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.admin_api:app", "--host", "0.0.0.0", "--port", "8000"])


@app.get("/admin/status", dependencies=[Depends(require_admin)])
async def status() -> dict[str, Any]:
    config = load_config()
    with open_db() as db:
        chats = db.list_chats()
        if not owner_actions_allowed():
            allowed_chat_ids = db.user_admin_chat_ids(current_actor_id() or 0)
            chats = [chat for chat in chats if chat.chat_id in allowed_chat_ids]
        can_view_stars = any(admin_feature_allowed(db, "stars", "view", chat_id=chat.chat_id) for chat in chats)
        can_view_mine = any(admin_feature_allowed(db, "mine", "view", chat_id=chat.chat_id) for chat in chats)
        can_view_participants = any(admin_feature_allowed(db, "participants", "view", chat_id=chat.chat_id) for chat in chats)
        stars = db.list_star_payments(limit=1000) if can_view_stars else []
        dig_players = db.list_all_dig_players() if can_view_mine else []
        participants = db.count_pickable_users_all() if can_view_participants else 0
        permissions = feature_permissions_for_actor(db)
        feature_permissions = feature_permission_modes_for_actor(db)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
    finally:
        await bot.session.close()

    return {
        "name": me.first_name,
        "username": me.username or "",
        "isRunning": True,
        "chats": len(chats),
        "participants": participants,
        "starPayments": len(stars),
        "starAmount": sum(int(item.amount) for item in stars),
        "digPlayers": len(dig_players),
        "ownerActionsAllowed": owner_actions_allowed(),
        "ownerOnlyActionsAllowed": config.owner_id is not None and current_actor_id() == config.owner_id,
        "currentUserId": current_actor_id(),
        "permissions": permissions,
        "featurePermissions": feature_permissions,
        "features": ADMIN_FEATURES,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.post("/admin/analytics", dependencies=[Depends(require_admin)])
def admin_analytics_event(payload: AnalyticsPayload) -> dict[str, Any]:
    with open_db() as db:
        event_id = save_analytics_event(db, payload, current_actor_id())
    return {"ok": True, "id": event_id}


@app.get("/admin/analytics", dependencies=[Depends(require_admin)])
def admin_analytics(limit: int = 100, app: str | None = None, eventType: str | None = None) -> dict[str, Any]:
    if not owner_actions_allowed():
        raise HTTPException(status_code=403, detail="Analytics is owner-only")
    with open_db() as db:
        return {
            "summary": db.device_events_summary(),
            "items": db.list_device_events(limit=limit, app=app, event_type=eventType),
        }


async def weather_payload(q: str, user_agent: str) -> dict[str, Any]:
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Укажи город или населенный пункт.")
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        geocode_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={quote(query)}&count=5&language=ru&format=json"
        )
        async with session.get(geocode_url, headers={"User-Agent": user_agent}) as response:
            if response.status != 200:
                raise HTTPException(status_code=502, detail="Геокодер временно недоступен.")
            data = await response.json(content_type=None)
        results = data.get("results") or []
        if not results:
            raise HTTPException(status_code=404, detail="Место не найдено.")
        place = results[0]
        location_parts = [str(place.get("name") or query)]
        for key in ("admin2", "admin1", "country"):
            value = place.get(key)
            if value and str(value) not in location_parts:
                location_parts.append(str(value))
        latitude = float(place["latitude"])
        longitude = float(place["longitude"])
        forecast_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
            "&timezone=auto"
        )
        async with session.get(forecast_url, headers={"User-Agent": user_agent}) as response:
            if response.status != 200:
                raise HTTPException(status_code=502, detail="Погода временно недоступна.")
            forecast = await response.json(content_type=None)
    current = forecast.get("current") or {}
    return {
        "location": ", ".join(location_parts),
        "temperature": current.get("temperature_2m"),
        "apparentTemperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "windSpeed": current.get("wind_speed_10m"),
        "weatherCode": current.get("weather_code"),
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get("/user/weather")
async def user_weather(
    q: str,
    user: Annotated[dict[str, Any], Depends(require_user)],
) -> dict[str, Any]:
    return await weather_payload(q, "MonkeyDin/0.3")


@app.get("/admin/weather", dependencies=[Depends(require_admin)])
async def admin_weather(q: str) -> dict[str, Any]:
    return await weather_payload(q, "tg-admin-bot-panel")


@app.get("/admin/chats", dependencies=[Depends(require_admin)])
def chats() -> list[dict[str, Any]]:
    with open_db() as db:
        items = []
        for chat in db.list_chats():
            chat_id = chat.chat_id
            if not owner_actions_allowed() and chat_id not in db.user_admin_chat_ids(current_actor_id() or 0):
                continue
            can_replies = admin_feature_allowed(db, "addReply", "view", chat_id) or admin_feature_allowed(db, "deleteReply", "view", chat_id)
            can_triggers = admin_feature_allowed(db, "triggers", "view", chat_id)
            can_blacklist = admin_feature_allowed(db, "blacklist", "view", chat_id)
            can_quotes = admin_feature_allowed(db, "quotes", "view", chat_id)
            can_giveaway = admin_feature_allowed(db, "giveaway", "view", chat_id)
            can_ads = admin_feature_allowed(db, "ads", "view", chat_id)
            items.append(
                {
                    **dump(chat),
                    "replies": len(db.list_replies(chat_id)) if can_replies else 0,
                    "triggers": len(db.list_triggers(chat_id)) if can_triggers else 0,
                    "blacklistWords": len(db.list_blacklist_words(chat_id)) if can_blacklist else 0,
                    "quotes": len(db.list_quotes(chat_id)) if can_quotes else 0,
                    "birthdays": len(db.list_birthdays(chat_id)) if can_giveaway else 0,
                    "advertisements": len(db.list_advertisements(chat_id)) if can_ads else 0,
                    "alarmEnabled": bool(db.get_alarm_settings(chat_id).enabled),
                }
            )
        return items


@app.get("/admin/chats/{chat_id}/overview", dependencies=[Depends(require_admin)])
def chat_overview(chat_id: int) -> dict[str, Any]:
    with open_db() as db:
        require_chat(db, chat_id)
        chat = db.get_chat(chat_id)
        can_replies = admin_feature_allowed(db, "addReply", "view") or admin_feature_allowed(db, "deleteReply", "view")
        can_triggers = admin_feature_allowed(db, "triggers", "view")
        can_blacklist = admin_feature_allowed(db, "blacklist", "view")
        can_quotes = admin_feature_allowed(db, "quotes", "view")
        can_giveaway = admin_feature_allowed(db, "giveaway", "view")
        can_roll_mute = admin_feature_allowed(db, "rollMute", "view")
        can_quiet = admin_feature_allowed(db, "quiet", "view")
        can_participants = admin_feature_allowed(db, "participants", "view")
        can_ads = admin_feature_allowed(db, "ads", "view")
        return {
            "chat": dump(chat),
            "replies": dump(db.list_replies(chat_id)) if can_replies else [],
            "triggers": dump(db.list_triggers(chat_id)) if can_triggers else [],
            "blacklist": dump(db.list_blacklist_words(chat_id)) if can_blacklist else [],
            "quotes": dump(db.list_quotes(chat_id)) if can_quotes else [],
            "birthdays": dump(db.list_birthdays(chat_id)) if can_giveaway else [],
            "advertisements": dump_advertisements(db, chat_id) if can_ads else [],
            "topics": dump(db.list_topics(chat_id)) if can_ads else [],
            "alarm": dump(db.get_alarm_settings(chat_id)),
            "giveaway": dump(db.get_giveaway_settings(chat_id)) if can_giveaway else None,
            "rollMute": dump(db.get_roll_mute_settings(chat_id)) if can_roll_mute else None,
            "quiet": dump(db.get_quiet_settings(chat_id)) if can_quiet else None,
            "giveawayTop": dump(db.top_giveaway_stats(chat_id, limit=10)) if can_giveaway else [],
            "rollMuteTop": dump(db.top_roll_mute_stats(chat_id, limit=10)) if can_roll_mute else [],
            "participants": dump(db.list_pickable_users(chat_id)) if can_participants else [],
            "permissions": feature_permissions_for_actor(db, chat_id),
            "featurePermissions": feature_permission_modes_for_actor(db, chat_id),
        }


@app.get("/admin/chats/{chat_id}/admins", dependencies=[Depends(require_admin)])
async def chat_admins(chat_id: int) -> dict[str, Any]:
    require_owner_action()
    config = load_config()
    with open_db() as db:
        require_chat(db, chat_id)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        members = await bot.get_chat_administrators(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read chat admins: {exc}") from exc
    finally:
        await bot.session.close()
    admins = []
    for member in members:
        user = member.user
        if user.is_bot:
            continue
        admins.append(
            {
                "userId": user.id,
                "username": user.username or "",
                "fullName": user.full_name,
                "status": str(getattr(member, "status", "")),
            }
        )
    return {"admins": admins}


@app.get("/admin/chats/{chat_id}/participants/top", dependencies=[Depends(require_admin)])
def participant_top(chat_id: int, period: str = "day", limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(50, int(limit)))
    since = participant_since_date(period)
    with open_db() as db:
        require_admin_feature(db, "participants", mode="view")
        require_chat(db, chat_id)
        items = db.top_participant_activity(chat_id, since_date=since, limit=safe_limit)
    return {"period": period, "since": since, "items": dump(items)}


@app.get("/admin/chats/{chat_id}/logs", dependencies=[Depends(require_admin)])
def audit_logs(chat_id: int, limit: int = 100) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "logs", mode="view")
        require_chat(db, chat_id)
        return {"items": dump(db.list_audit_logs(chat_id, limit=limit))}


@app.post("/admin/chats/{chat_id}/message", dependencies=[Depends(require_admin)])
async def send_message(chat_id: int, payload: TextPayload) -> dict[str, Any]:
    config = load_config()
    with open_db() as db:
        require_admin_feature(db, "send.text")
        require_chat(db, chat_id)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        message = await bot.send_message(chat_id=chat_id, text=payload.text, parse_mode=None)
    finally:
        await bot.session.close()
    return {"ok": True, "message": "sent", "messageId": message.message_id}


@app.post("/admin/chats/{chat_id}/media", dependencies=[Depends(require_admin)])
async def send_media(chat_id: int, payload: MediaPayload) -> dict[str, Any]:
    config = load_config()
    with open_db() as db:
        require_admin_feature(db, "send.voice" if payload.asVoice else "send.media")
        require_chat(db, chat_id)

    try:
        data = base64.b64decode(payload.dataBase64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid media data") from exc

    if len(data) > 45 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File is too large")

    filename = payload.filename.strip() or "file"
    mime = payload.mimeType.lower().strip()
    file = BufferedInputFile(data, filename=filename)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        if payload.asVoice:
            message = await bot.send_voice(chat_id=chat_id, voice=file, caption=payload.caption, parse_mode=None)
        elif mime.startswith("image/"):
            message = await bot.send_photo(chat_id=chat_id, photo=file, caption=payload.caption, parse_mode=None)
        elif mime.startswith("video/"):
            message = await bot.send_video(chat_id=chat_id, video=file, caption=payload.caption, parse_mode=None)
        elif mime.startswith("audio/"):
            message = await bot.send_audio(chat_id=chat_id, audio=file, caption=payload.caption, parse_mode=None)
        else:
            message = await bot.send_document(chat_id=chat_id, document=file, caption=payload.caption, parse_mode=None)
    finally:
        await bot.session.close()

    return {"ok": True, "message": "media sent", "messageId": message.message_id}


@app.post("/admin/feedback", dependencies=[Depends(require_admin)])
async def feedback(payload: TextPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "feedback.send")
    config = load_config()
    if not config.bot_admin_ids:
        raise HTTPException(status_code=400, detail="BOT_ADMIN_IDS is empty")

    actor_id = current_actor_id()
    reply_markup = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ответить", callback_data=f"feedback:reply:{actor_id}")],
            ]
        )
        if actor_id is not None
        else None
    )
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    sent = 0
    try:
        for admin_id in config.bot_admin_ids:
            actor_text = f"\nОт: <code>{actor_id}</code>" if actor_id is not None else ""
            await bot.send_message(
                admin_id,
                f"<b>Обратная связь из панели</b>{actor_text}\n\n{escape(payload.text)}",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            sent += 1
    finally:
        await bot.session.close()

    return {"ok": True, "message": f"sent to {sent} admins"}

@app.post("/admin/chats/{chat_id}/check-access", dependencies=[Depends(require_admin)])
async def check_access(chat_id: int) -> dict[str, Any]:
    config = load_config()
    with open_db() as db:
        require_admin_feature(db, "checkAccess")
        chat = db.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        status_text = str(member.status).split(".")[-1].lower()
        can_delete = bool(getattr(member, "can_delete_messages", False))
        can_restrict = bool(getattr(member, "can_restrict_members", False))
        can_invite = bool(getattr(member, "can_invite_users", False))
    except Exception:
        status_text = "нет доступа"
        can_delete = False
        can_restrict = False
        can_invite = False
    finally:
        await bot.session.close()

    return {
        "ok": True,
        "chatId": chat_id,
        "title": chat.title,
        "status": status_text,
        "canDeleteMessages": can_delete,
        "canRestrictMembers": can_restrict,
        "canInviteUsers": can_invite,
    }


@app.post("/admin/restart", dependencies=[Depends(require_admin)])
async def restart() -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "restart")
    asyncio.create_task(restart_admin_api())
    return ok("restarting")


@app.post("/admin/chats/{chat_id}/replies", dependencies=[Depends(require_admin)])
async def set_reply(chat_id: int, payload: ReplyPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "addReply")
        require_chat(db, chat_id)
        db.set_reply(chat_id, payload.username, payload.text, current_actor_id())
    await notify_staff_autoreply_change(f"@ответ @{normalize_username(payload.username)} изменён через веб-панель для чата {chat_id}.")
    return ok(f"reply for @{normalize_username(payload.username)} saved")


@app.delete("/admin/chats/{chat_id}/replies/{username}", dependencies=[Depends(require_admin)])
async def delete_reply(chat_id: int, username: str) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "deleteReply")
        require_chat(db, chat_id)
        deleted = db.delete_reply(chat_id, username)
    if deleted:
        await notify_staff_autoreply_change(f"@ответ @{normalize_username(username)} удалён через веб-панель из чата {chat_id}.")
    return ok("deleted" if deleted else "not found")


@app.post("/admin/chats/{chat_id}/triggers", dependencies=[Depends(require_admin)])
async def set_trigger(chat_id: int, payload: TriggerPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "triggers.add")
        require_chat(db, chat_id)
        db.set_trigger(chat_id, payload.trigger, payload.text, current_actor_id())
    await notify_staff_autoreply_change(f"Триггер «{normalize_trigger(payload.trigger)}» изменён через веб-панель для чата {chat_id}.")
    return ok(f"trigger '{normalize_trigger(payload.trigger)}' saved")


@app.delete("/admin/chats/{chat_id}/triggers/{trigger}", dependencies=[Depends(require_admin)])
async def delete_trigger(chat_id: int, trigger: str) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "triggers.delete")
        require_chat(db, chat_id)
        deleted = db.delete_trigger(chat_id, trigger)
    if deleted:
        await notify_staff_autoreply_change(f"Триггер «{normalize_trigger(trigger)}» удалён через веб-панель из чата {chat_id}.")
    return ok("deleted" if deleted else "not found")


@app.post("/admin/chats/{chat_id}/blacklist", dependencies=[Depends(require_admin)])
def add_blacklist_word(chat_id: int, payload: WordPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "blacklist.add")
        require_chat(db, chat_id)
        db.add_blacklist_word(chat_id, payload.word, current_actor_id())
    return ok("word added")


@app.delete("/admin/chats/{chat_id}/blacklist/{word}", dependencies=[Depends(require_admin)])
def delete_blacklist_word(chat_id: int, word: str) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "blacklist.delete")
        require_chat(db, chat_id)
        deleted = db.delete_blacklist_word(chat_id, word)
    return ok("deleted" if deleted else "not found")


@app.post("/admin/chats/{chat_id}/alarm", dependencies=[Depends(require_admin)])
def update_alarm(chat_id: int, payload: AlarmPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "alarm.toggle" if payload.enabled is not None and payload.alarmText is None and payload.clearText is None else "alarm.text")
        require_chat(db, chat_id)
        if payload.enabled is not None:
            db.set_alarm_enabled(chat_id, payload.enabled, current_actor_id())
        if payload.alarmText is not None or payload.clearText is not None:
            db.set_alarm_texts(chat_id, payload.alarmText, payload.clearText, current_actor_id())
    return ok("alarm updated")


@app.post("/admin/chats/{chat_id}/roll-mute", dependencies=[Depends(require_admin)])
def update_roll_mute(chat_id: int, payload: RollMutePayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "rollMute.settings")
        require_chat(db, chat_id)
        db.set_roll_mute_settings(chat_id, payload.muteMinutes, payload.cooldownMinutes, current_actor_id())
    return ok("roll mute updated")


@app.post("/admin/chats/{chat_id}/quiet", dependencies=[Depends(require_admin)])
def update_quiet(chat_id: int, payload: QuietPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "quiet.text")
        require_chat(db, chat_id)
        db.set_quiet_text(chat_id, payload.replyText, current_actor_id())
    return ok("quiet text updated")


@app.post("/admin/chats/{chat_id}/quiet/manual", dependencies=[Depends(require_admin)])
async def quiet_manual(chat_id: int, payload: QuietManualPayload) -> dict[str, Any]:
    config = load_config()
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        with open_db() as db:
            require_admin_feature(db, "quiet.manual")
            require_chat(db, chat_id)
            target_id, target_name = await resolve_quiet_target(bot, db, chat_id, payload.target)
            try:
                member = await bot.get_chat_member(chat_id, target_id)
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                raise HTTPException(status_code=400, detail=f"User not found in chat: {exc}") from exc
            status = str(getattr(member.status, "value", member.status))
            if status in {"creator", "administrator"}:
                raise HTTPException(status_code=400, detail="Cannot restrict chat admin")

            until_date = datetime.now(timezone.utc) + timedelta(minutes=payload.minutes)
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_audios=False,
                    can_send_documents=False,
                    can_send_photos=False,
                    can_send_videos=False,
                    can_send_video_notes=False,
                    can_send_voice_notes=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_react_to_messages=False,
                ),
                until_date=until_date,
                use_independent_chat_permissions=True,
            )
            settings = db.get_quiet_settings(chat_id)
            text = render_quiet_reply(settings.reply_text, target_name, payload.minutes, payload.reason.strip())
            sent = await bot.send_message(chat_id, text, disable_web_page_preview=True)
            await send_saved_quiet_media(bot, chat_id, settings.media_type, settings.media_file_id, sent.message_id)
    finally:
        await bot.session.close()
    return ok("user restricted")


@app.post("/admin/chats/{chat_id}/quiet/media", dependencies=[Depends(require_admin)])
async def set_quiet_media(chat_id: int, payload: QuietMediaPayload) -> dict[str, Any]:
    config = load_config()
    actor_id = current_actor_id()
    if actor_id is None:
        raise HTTPException(status_code=400, detail="Current admin actor is unknown")

    try:
        data = base64.b64decode(payload.dataBase64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid media data") from exc
    if len(data) > 45 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File is too large")

    filename = payload.filename.strip() or "quiet-media"
    mime = payload.mimeType.lower().strip()
    file = BufferedInputFile(data, filename=filename)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        with open_db() as db:
            require_admin_feature(db, "quiet.mediaSave")
            require_chat(db, chat_id)

        if payload.asVoice:
            sent = await bot.send_voice(actor_id, file, caption="Медиа для команды затихни сохранено.")
            media_type = "voice"
            file_id = sent.voice.file_id if sent.voice else None
        elif mime == "image/gif" or filename.lower().endswith(".gif"):
            sent = await bot.send_animation(actor_id, file, caption="Медиа для команды затихни сохранено.")
            media_type = "animation"
            file_id = sent.animation.file_id if sent.animation else None
        elif mime.startswith("audio/"):
            sent = await bot.send_audio(actor_id, file, caption="Медиа для команды затихни сохранено.")
            media_type = "audio"
            file_id = sent.audio.file_id if sent.audio else None
        else:
            raise HTTPException(status_code=400, detail="Quiet media supports GIF, voice, or audio")

        if not file_id:
            raise HTTPException(status_code=400, detail="Telegram did not return media file id")

        with open_db() as db:
            db.set_quiet_media(chat_id, media_type, file_id, actor_id)
    finally:
        await bot.session.close()
    return {"ok": True, "message": "quiet media saved", "mediaType": media_type}


@app.delete("/admin/chats/{chat_id}/quiet/media", dependencies=[Depends(require_admin)])
def delete_quiet_media(chat_id: int) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "quiet.mediaDelete")
        require_chat(db, chat_id)
        db.clear_quiet_media(chat_id, current_actor_id())
    return ok("quiet media deleted")


@app.post("/admin/chats/{chat_id}/giveaway", dependencies=[Depends(require_admin)])
def update_giveaway(chat_id: int, payload: GiveawayPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "giveaway.settings")
        require_chat(db, chat_id)
        db.set_giveaway_settings(
            chat_id,
            payload.trigger,
            payload.title,
            payload.winnersCount,
            current_actor_id(),
        )
    return ok("giveaway updated")


@app.post("/admin/chats/{chat_id}/birthdays", dependencies=[Depends(require_admin)])
def add_birthday(chat_id: int, payload: BirthdayPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "giveaway.birthdays")
        require_chat(db, chat_id)
        db.add_birthday(chat_id, payload.day, payload.month, payload.text, current_actor_id())
    return ok("birthday added")


@app.delete("/admin/chats/{chat_id}/birthdays/{birthday_id}", dependencies=[Depends(require_admin)])
def delete_birthday(chat_id: int, birthday_id: int) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "giveaway.birthdays")
        require_chat(db, chat_id)
        deleted = db.delete_birthday(chat_id, birthday_id)
    return ok("deleted" if deleted else "not found")


async def upload_advertisement_attachments(
    bot: Bot,
    actor_id: int,
    attachments: list[AdvertisementAttachmentPayload],
) -> list[tuple[str, str, str]]:
    uploaded: list[tuple[str, str, str]] = []
    total_size = 0
    for attachment in attachments:
        try:
            data = base64.b64decode(attachment.dataBase64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid media data: {attachment.filename}") from exc
        total_size += len(data)
        if len(data) > 45 * 1024 * 1024 or total_size > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Advertisement attachments are too large")

        file = BufferedInputFile(data, filename=attachment.filename)
        try:
            if attachment.mimeType.lower().startswith("image/"):
                sent = await bot.send_photo(actor_id, file, caption="Фото для рекламы сохранено.", parse_mode=None)
                if not sent.photo:
                    raise HTTPException(status_code=400, detail="Telegram did not return photo file id")
                uploaded.append(("photo", sent.photo[-1].file_id, attachment.filename))
            elif attachment.mimeType.lower().startswith("video/"):
                sent = await bot.send_video(actor_id, file, caption="Видео для рекламы сохранено.", parse_mode=None)
                if not sent.video:
                    raise HTTPException(status_code=400, detail="Telegram did not return video file id")
                uploaded.append(("video", sent.video.file_id, attachment.filename))
            else:
                raise HTTPException(status_code=400, detail="Advertisement supports only photos and videos")
            try:
                await bot.delete_message(actor_id, sent.message_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            raise HTTPException(status_code=400, detail=f"Cannot save advertisement media: {exc}") from exc
    return uploaded


async def publish_advertisement_now(bot: Bot, db: Database, advertisement_id: int) -> None:
    advertisement = next(
        (
            item
            for chat in db.list_chats()
            for item in db.list_advertisements(chat.chat_id)
            if item.id == advertisement_id
        ),
        None,
    )
    if advertisement is None:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    thread_kwargs = {"message_thread_id": advertisement.topic_thread_id} if advertisement.topic_thread_id else {}
    attachments = db.list_advertisement_attachments(advertisement.id)
    try:
        if attachments:
            caption = advertisement.text if len(advertisement.text) <= 1024 else None
            media = [
                (
                    InputMediaPhoto(media=item.file_id, caption=caption if position == 0 else None, parse_mode=None)
                    if item.media_type == "photo"
                    else InputMediaVideo(media=item.file_id, caption=caption if position == 0 else None, parse_mode=None)
                )
                for position, item in enumerate(attachments)
            ]
            if len(media) == 1:
                item = attachments[0]
                if item.media_type == "photo":
                    await bot.send_photo(advertisement.chat_id, item.file_id, caption=caption, parse_mode=None, **thread_kwargs)
                else:
                    await bot.send_video(advertisement.chat_id, item.file_id, caption=caption, parse_mode=None, **thread_kwargs)
            else:
                await bot.send_media_group(advertisement.chat_id, media=media, **thread_kwargs)
            if caption is None:
                await bot.send_message(advertisement.chat_id, advertisement.text, parse_mode=None, **thread_kwargs)
        else:
            await bot.send_message(advertisement.chat_id, advertisement.text, parse_mode=None, **thread_kwargs)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        db.mark_advertisement_failed(advertisement.id, str(exc))
        raise HTTPException(status_code=400, detail=f"Реклама не отправлена: {exc}") from exc
    db.mark_advertisement_sent(advertisement.id, datetime.now().astimezone().isoformat(timespec="seconds"))


@app.post("/admin/chats/{chat_id}/advertisements", dependencies=[Depends(require_admin)])
async def add_advertisement(chat_id: int, payload: AdvertisementPayload) -> dict[str, Any]:
    scheduled_at = advertisement_scheduled_at(payload)
    actor_id = current_actor_id()
    if actor_id is None:
        raise HTTPException(status_code=400, detail="Current admin actor is unknown")
    with open_db() as db:
        require_admin_feature(db, "ads.add")
        require_admin_feature(db, "ads.settings")
        require_chat(db, chat_id)
    config = load_config()
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        attachments = await upload_advertisement_attachments(bot, actor_id, payload.attachments)
    finally:
        await bot.session.close()
    with open_db() as db:
        ad_id = db.add_advertisement(
            chat_id,
            payload.text,
            payload.enabled,
            payload.startTime,
            payload.intervalMinutes,
            payload.durationType,
            payload.startMode,
            scheduled_at,
            payload.topicThreadId,
            actor_id,
        )
        db.replace_advertisement_attachments(ad_id, attachments)
    if payload.enabled and payload.startMode == "now":
        bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            with open_db() as db:
                await publish_advertisement_now(bot, db, ad_id)
        finally:
            await bot.session.close()
    return {"ok": True, "id": ad_id}


@app.put("/admin/chats/{chat_id}/advertisements/{ad_id}", dependencies=[Depends(require_admin)])
async def edit_advertisement(chat_id: int, ad_id: int, payload: AdvertisementPayload) -> dict[str, Any]:
    scheduled_at = advertisement_scheduled_at(payload)
    actor_id = current_actor_id()
    if actor_id is None:
        raise HTTPException(status_code=400, detail="Current admin actor is unknown")
    with open_db() as db:
        require_admin_feature(db, "ads.edit")
        require_admin_feature(db, "ads.settings")
        require_chat(db, chat_id)
    attachments: list[tuple[str, str, str]] | None = None
    if payload.replaceAttachments:
        config = load_config()
        bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            attachments = await upload_advertisement_attachments(bot, actor_id, payload.attachments)
        finally:
            await bot.session.close()
    with open_db() as db:
        changed = db.update_advertisement(
            chat_id,
            ad_id,
            payload.text,
            payload.enabled,
            payload.startTime,
            payload.intervalMinutes,
            payload.durationType,
            payload.startMode,
            scheduled_at,
            payload.topicThreadId,
        )
        if changed and attachments is not None:
            db.replace_advertisement_attachments(ad_id, attachments)
    if changed and payload.enabled and payload.startMode == "now":
        config = load_config()
        bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            with open_db() as db:
                await publish_advertisement_now(bot, db, ad_id)
        finally:
            await bot.session.close()
    return ok("updated" if changed else "not found")


@app.delete("/admin/chats/{chat_id}/advertisements/{ad_id}", dependencies=[Depends(require_admin)])
def delete_advertisement(chat_id: int, ad_id: int) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "ads.delete")
        require_chat(db, chat_id)
        deleted = db.delete_advertisement(chat_id, ad_id)
    return ok("deleted" if deleted else "not found")


@app.put("/admin/chats/{chat_id}/topics/{thread_id}", dependencies=[Depends(require_admin)])
def rename_topic(chat_id: int, thread_id: int, payload: TopicTitlePayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "ads.settings")
        require_chat(db, chat_id)
        db.upsert_topic(chat_id, thread_id, payload.title.strip())
    return ok("topic renamed")


@app.post("/admin/chats/{chat_id}/quotes", dependencies=[Depends(require_admin)])
def add_quote(chat_id: int, payload: TextPayload) -> dict[str, Any]:
    with open_db() as db:
        require_admin_feature(db, "quotes.add")
        require_chat(db, chat_id)
        db.add_quote(chat_id, payload.text, None, current_actor_id())
    return ok("quote added")


@app.delete("/admin/chats/{chat_id}/quotes/{quote_id}", dependencies=[Depends(require_admin)])
def delete_quote(chat_id: int, quote_id: int) -> dict[str, Any]:
    require_owner_action()
    with open_db() as db:
        require_admin_feature(db, "quotes.delete")
        require_chat(db, chat_id)
        deleted = db.delete_quote(chat_id, quote_id)
    return ok("deleted" if deleted else "not found")


@app.get("/admin/stars/payments", dependencies=[Depends(require_admin)])
def star_payments(limit: int = 25) -> list[dict[str, Any]]:
    with open_db() as db:
        require_admin_feature(db, "stars", mode="view")
        return dump(db.list_star_payments(limit=max(1, min(100, limit))))


@app.get("/admin/premium/subscriptions", dependencies=[Depends(require_admin)])
def admin_premium_subscriptions() -> dict[str, Any]:
    require_owner_action()
    premium = PremiumService(load_config().db_path)
    try:
        items = []
        now = datetime.now(timezone.utc)
        for row in premium.list_subscriptions():
            item = dict(row)
            try:
                item["active"] = item["status"] == "active" and datetime.fromisoformat(item["expires_at"]) > now
            except (TypeError, ValueError):
                item["active"] = False
            item["planTitle"] = PLANS[item["plan"]].title if item["plan"] in PLANS else item["plan"]
            items.append(item)
        return {"items": items, "total": len(items)}
    finally:
        premium.close()


@app.post("/admin/premium/grant", dependencies=[Depends(require_admin)])
def admin_premium_grant(payload: PremiumGrantPayload) -> dict[str, Any]:
    require_owner_action()
    premium = PremiumService(load_config().db_path)
    try:
        now = datetime.now(timezone.utc)
        base = now
        current = premium.get_user_subscription(payload.userId)
        if current and current["status"] == "active" and current["plan"] == payload.plan:
            try:
                current_expiry = datetime.fromisoformat(current["expires_at"])
                if current_expiry > now:
                    base = current_expiry
            except (TypeError, ValueError):
                pass
        expires_at = base + timedelta(days=payload.days)
        subscription = premium.activate_subscription(
            user_id=payload.userId,
            plan=payload.plan,
            telegram_payment_charge_id=f"manual:{current_actor_id() or 'unknown'}",
            provider_payment_charge_id=None,
            expires_at=expires_at,
        )
        premium.log(
            "INFO",
            f"Premium granted manually: actor={current_actor_id()}, user={payload.userId}, plan={payload.plan}, days={payload.days}",
        )
        return {"ok": True, "subscription": dict(subscription) if subscription else None}
    finally:
        premium.close()


@app.get("/admin/dig/top", dependencies=[Depends(require_admin)])
def dig_top(limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(100, limit))
    with open_db() as db:
        require_admin_feature(db, "mine", mode="view")
        return {
            "depth": dump(db.top_dig_depth(0, limit=limit)),
            "coins": dump(db.top_dig_coins(0, limit=limit)),
        }


@app.get("/admin/dig/players", dependencies=[Depends(require_admin)])
def dig_players(page: int = 1, per_page: int = 20) -> dict[str, Any]:
    safe_page = max(1, int(page))
    safe_per_page = max(1, min(50, int(per_page)))
    offset = (safe_page - 1) * safe_per_page
    with open_db() as db:
        require_admin_feature(db, "mine", mode="view")
        total = db.count_dig_players()
        players = db.list_dig_players_page(limit=safe_per_page, offset=offset)
        items = []
        for player in players:
            item = dump(player)
            item["extraDigs"] = db.get_dig_item_quantity(0, player.user_id, "star_dig")
            items.append(item)
        return {"items": items, "total": total, "page": safe_page, "perPage": safe_per_page}


@app.post("/admin/dig/grant", dependencies=[Depends(require_admin)])
def dig_grant(payload: DigGrantPayload) -> dict[str, Any]:
    require_owner_action()
    with open_db() as db:
        require_admin_feature(db, "mine.grant")
        if payload.goldenTickets is not None or payload.superPasses is not None:
            require_owner_only()
            if db.get_dig_player(0, payload.userId) is None:
                raise HTTPException(status_code=404, detail="Игрок шахты с таким User ID не зарегистрирован.")
        if payload.coins is not None:
            db.add_dig_coins(0, payload.userId, payload.coins)
        if payload.luck is not None:
            db.set_dig_luck(0, payload.userId, payload.luck, utc_now())
        if payload.extraDigs is not None:
            db.adjust_dig_item(0, payload.userId, "star_dig", payload.extraDigs)
        if payload.goldenTickets is not None:
            db.adjust_dig_item(0, payload.userId, "golden_ticket", payload.goldenTickets)
        if payload.superPasses is not None:
            db.adjust_dig_item(0, payload.userId, "super_game_pass", payload.superPasses)
        if payload.clearCooldown:
            db.clear_dig_cooldown(0, payload.userId)
    return ok("dig player updated")

