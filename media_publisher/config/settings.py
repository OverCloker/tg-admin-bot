from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PublisherSettings:
    folder: str = ""
    bot_token: str = ""
    chat_id: str = ""
    thread_id: str = ""
    selected_destination: str = "Фильмы"
    topic_ids: dict[str, str] = field(default_factory=dict)
    tmdb_api_key: str = ""
    omdb_api_key: str = ""
    rezka_domain: str = ""
    after_publish: str = "leave"

    @classmethod
    def load(cls, path: str | Path) -> "PublisherSettings":
        config_path = Path(path)
        data: dict = {}
        if config_path.is_file():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        settings = cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})
        settings.bot_token = settings.bot_token or os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("BOT_TOKEN", ""))
        settings.chat_id = settings.chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        settings.thread_id = settings.thread_id or os.getenv("TELEGRAM_THREAD_ID", "")
        if settings.thread_id and settings.selected_destination not in settings.topic_ids:
            settings.topic_ids[settings.selected_destination] = settings.thread_id
        return settings

    def save(self, path: str | Path) -> None:
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
