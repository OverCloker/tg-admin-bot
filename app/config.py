from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    bot_admin_ids: set[int]
    openai_api_key: str | None
    openai_model: str


def load_config() -> Config:
    project_env = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(project_env, encoding="utf-8-sig")
    load_dotenv(encoding="utf-8-sig")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "123456:replace_with_token_from_botfather":
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add your BotFather token.")

    admin_ids_raw = os.getenv("BOT_ADMIN_IDS", "").strip()
    admin_ids: set[int] = set()
    if admin_ids_raw:
        for item in admin_ids_raw.replace(";", ",").split(","):
            item = item.strip()
            if item:
                admin_ids.add(int(item))

    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "bot.sqlite3").strip() or "bot.sqlite3",
        bot_admin_ids=admin_ids,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
    )
