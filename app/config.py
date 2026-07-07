from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    bot_admin_ids: set[int]
    owner_id: int | None
    alerts_api_token: str | None


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

    owner_id_raw = os.getenv("OWNER_ID", "").strip()
    owner_id = int(owner_id_raw) if owner_id_raw else (min(admin_ids) if admin_ids else None)

    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "bot.sqlite3").strip() or "bot.sqlite3",
        bot_admin_ids=admin_ids,
        owner_id=owner_id,
        alerts_api_token=os.getenv("ALERTS_API_TOKEN", "").strip() or None,
    )
