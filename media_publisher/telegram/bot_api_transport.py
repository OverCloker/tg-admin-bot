from __future__ import annotations

import json
from pathlib import Path

import aiohttp

from .base_transport import TelegramTransport


class TelegramApiError(RuntimeError):
    pass


class BotApiTransport(TelegramTransport):
    """Outgoing-only Bot API transport; it never calls getUpdates/webhooks."""

    CLOUD_UPLOAD_LIMIT = 50 * 1024 * 1024
    LOCAL_UPLOAD_LIMIT = 2000 * 1024 * 1024

    def __init__(self, token: str, timeout_seconds: int = 1800, api_url: str = "https://api.telegram.org"):
        self.token = token.strip()
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.api_url = (api_url.strip() or "https://api.telegram.org").rstrip("/")

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/bot{self.token}"

    @property
    def max_upload_bytes(self) -> int:
        return self.CLOUD_UPLOAD_LIMIT if self.api_url.casefold() == "https://api.telegram.org" else self.LOCAL_UPLOAD_LIMIT

    def validate_uploads(self, paths: list[Path]) -> None:
        oversized = [(path, path.stat().st_size) for path in paths if path.is_file() and path.stat().st_size > self.max_upload_bytes]
        if not oversized:
            return
        path, size = max(oversized, key=lambda item: item[1])
        current = size / (1024 * 1024)
        limit = self.max_upload_bytes / (1024 * 1024)
        if self.max_upload_bytes == self.CLOUD_UPLOAD_LIMIT:
            raise TelegramApiError(
                f"Видео «{path.name}» занимает {current:.1f} МБ, облачный Telegram Bot API допускает до {limit:.0f} МБ. "
                "Карточка не отправлена. Настройте локальный Bot API server и укажите его адрес в поле «Bot API URL» — "
                "он поддерживает файлы до 2000 МБ."
            )
        raise TelegramApiError(f"Видео «{path.name}» занимает {current:.1f} МБ и превышает лимит текущего Bot API server: {limit:.0f} МБ.")

    async def _request(self, method: str, data: dict | None = None, form: aiohttp.FormData | None = None):
        if not self.token:
            raise TelegramApiError("Токен Telegram не настроен.")
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(f"{self.base_url}/{method}", data=form or data) as response:
                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ClientError) as exc:
                    if response.status == 413:
                        raise TelegramApiError(
                            "Bot API отклонил загрузку: файл или HTTP-запрос слишком большой. "
                            "Проверьте лимит сервера и reverse proxy (HTTP 413)."
                        ) from exc
                    raise TelegramApiError(f"Telegram вернул некорректный ответ (HTTP {response.status}).") from exc
        if not payload.get("ok"):
            if response.status == 413:
                raise TelegramApiError(
                    "Bot API отклонил загрузку: файл или HTTP-запрос слишком большой (HTTP 413). "
                    "Для видео больше 50 МБ используйте локальный Bot API server; для своего reverse proxy увеличьте лимит тела запроса."
                )
            raise TelegramApiError(str(payload.get("description") or f"Ошибка Telegram API: {method}"))
        return payload.get("result")

    async def test_connection(self) -> dict:
        return await self._request("getMe", data={})

    @staticmethod
    def _chat_data(chat_id: str, thread_id: str) -> dict:
        data = {"chat_id": str(chat_id).strip()}
        if str(thread_id).strip():
            data["message_thread_id"] = str(thread_id).strip()
        return data

    async def send_message(self, text: str, chat_id: str, thread_id: str = "") -> dict:
        data = self._chat_data(chat_id, thread_id)
        data["text"] = text
        return await self._request("sendMessage", data=data)

    async def send_photo(self, photo: str | Path, caption: str, chat_id: str, thread_id: str = "") -> dict:
        path = Path(photo)
        if path.is_file():
            form = aiohttp.FormData()
            for key, value in self._chat_data(chat_id, thread_id).items():
                form.add_field(key, value)
            with path.open("rb") as handle:
                form.add_field("photo", handle, filename=path.name)
                form.add_field("caption", caption)
                return await self._request("sendPhoto", form=form)
        data = self._chat_data(chat_id, thread_id)
        data.update({"photo": str(photo), "caption": caption})
        return await self._request("sendPhoto", data=data)

    async def _send_file(self, method: str, field: str, source: str | Path, caption: str, chat_id: str, thread_id: str) -> dict:
        path = Path(source)
        if not path.is_file():
            raise TelegramApiError(f"Файл не найден: {path}")
        form = aiohttp.FormData()
        for key, value in self._chat_data(chat_id, thread_id).items():
            form.add_field(key, value)
        with path.open("rb") as handle:
            content_type = "video/mp4" if method == "sendVideo" else "application/octet-stream"
            form.add_field(field, handle, filename=path.name, content_type=content_type)
            if caption:
                form.add_field("caption", caption)
            return await self._request(method, form=form)

    async def send_video(self, video: str | Path, caption: str, chat_id: str, thread_id: str = "") -> dict:
        return await self._send_file("sendVideo", "video", video, caption, chat_id, thread_id)

    async def send_document(self, document: str | Path, caption: str, chat_id: str, thread_id: str = "") -> dict:
        return await self._send_file("sendDocument", "document", document, caption, chat_id, thread_id)

    async def send_media_group(self, files: list[Path], caption: str, chat_id: str, thread_id: str = "") -> list[dict]:
        if not files:
            return []
        if len(files) > 10:
            raise TelegramApiError("В одной медиагруппе Telegram разрешено не более 10 файлов.")
        form = aiohttp.FormData()
        for key, value in self._chat_data(chat_id, thread_id).items():
            form.add_field(key, value)
        media = []
        handles = []
        try:
            for index, path in enumerate(files):
                handle = path.open("rb")
                handles.append(handle)
                attach_name = f"media{index}"
                item = {"type": "video", "media": f"attach://{attach_name}"}
                if index == 0 and caption:
                    item["caption"] = caption
                media.append(item)
                form.add_field(attach_name, handle, filename=path.name, content_type="video/mp4")
            form.add_field("media", json.dumps(media, ensure_ascii=False))
            return await self._request("sendMediaGroup", form=form)
        finally:
            for handle in handles:
                handle.close()
