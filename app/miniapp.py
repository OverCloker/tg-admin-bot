"""Telegram Mini App for one-meter mine runs."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import base64
import time
from contextlib import suppress
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl
import aiohttp
from aiogram import Bot
from aiogram.types import LabeledPrice
from fastapi import APIRouter, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from .config import load_config
from .db import Database, normalize_trigger
from .dig_game import (
    INTERACTIVE_DIG_DURABILITY,
    INTERACTIVE_DIG_MAX_DEPTH,
    MINE_RESOURCE_CATALOG,
    MINE_RESOURCE_ORDER,
    cell_row_is_exhausted,
    cell_reward,
    collapse_payout,
    event_choice,
    final_cell_chance,
    final_depth_bonus,
    generate_dig_cells,
    generate_dig_stage,
    mined_resource_drops,
    mine_resource_prices,
    mine_type_for_total_depth,
    replacement_cell_stage,
    resolve_cell,
    resource_stack_text,
    scale_interactive_reward,
)
from .miniapp_ui import MINI_APP_HTML as MINI_APP_UI_HTML
from .premium import PremiumService
from .user_profile import build_user_profile

router = APIRouter()
DIG_LOCK = Lock()
TRIGGER_MEDIA_MAX_BYTES = 12 * 1024 * 1024
TRIGGER_MEDIA_TYPES = {
    "photo": {"image/jpeg", "image/png", "image/webp"},
    "animation": {"image/gif", "video/mp4"},
    "audio": {"audio/mpeg", "audio/mp3", "audio/ogg", "audio/wav", "audio/webm", "audio/mp4", "audio/x-m4a"},
}


class TicketPick(BaseModel):
    cell: int = Field(ge=0, le=8)


class SuperTicketPick(BaseModel):
    cell: int = Field(ge=0, le=80)


class ShopPurchase(BaseModel):
    item_key: str = Field(min_length=1, max_length=64)


class ProfileRoleSet(BaseModel):
    target: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=16)


class ProfileRoleClear(BaseModel):
    target: str = Field(min_length=1, max_length=64)


class MiniAppTriggerVariant(BaseModel):
    variantType: str = Field(default="text", min_length=1, max_length=32)
    text: str = Field(default="", max_length=4000)
    mediaType: str | None = Field(default=None, max_length=32)
    mediaFileId: str | None = Field(default=None, max_length=1000)


class MiniAppTriggerSave(BaseModel):
    chatId: int
    trigger: str = Field(min_length=1, max_length=120)
    text: str | None = Field(default=None, max_length=4000)
    variants: list[MiniAppTriggerVariant] = Field(default_factory=list, max_length=13)


class MiniAppTriggerDelete(BaseModel):
    chatId: int
    trigger: str = Field(min_length=1, max_length=120)


class MineAdminGrant(BaseModel):
    userId: int = Field(gt=0)
    coins: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    luck: int | None = Field(default=None, ge=0, le=100)
    extraDigs: int | None = Field(default=None, ge=-100, le=100)
    goldenTickets: int | None = Field(default=None, ge=-100, le=100)
    superPasses: int | None = Field(default=None, ge=-100, le=100)
    clearCooldown: bool = False


class MineAdminTarget(BaseModel):
    userId: int = Field(gt=0)
    reason: str = Field(default="", max_length=500)
    deletePlayer: bool = False


class ShopGiftSend(BaseModel):
    item_key: str = Field(min_length=1, max_length=64)
    target_user_id: int = Field(gt=0)


class MerchantSale(BaseModel):
    item_key: str | None = Field(default=None, min_length=1, max_length=64)


class ShiftContractPick(BaseModel):
    contract_key: str = Field(min_length=1, max_length=64)


class MineCellPick(BaseModel):
    cell: int = Field(ge=0, le=6)


class MineToolUse(BaseModel):
    item_key: str = Field(min_length=1, max_length=64)


class MineEventChoice(BaseModel):
    choice_key: str = Field(min_length=1, max_length=64)


def _ticket_public(db: Database, user_id: int) -> dict[str, Any] | None:
    game = db.get_gold_ticket_game(user_id)
    if not game:
        return None
    return {
        "active": True,
        "opened": json.loads(game["opened_json"] or "[]"),
        "attemptsLeft": int(game["attempts_left"]),
    }


def _super_ticket_public(db: Database, user_id: int) -> dict[str, Any] | None:
    game = db.get_super_ticket_game(user_id)
    if not game:
        return None
    return {
        "active": True,
        "opened": json.loads(game["opened_json"] or "[]"),
        "attemptsLeft": int(game["attempts_left"]),
    }


def _interactive_dig_public(db: Database, user_id: int) -> dict[str, Any] | None:
    session = db.get_active_interactive_dig_session(user_id)
    if not session:
        return None
    stage = json.loads(session["cells_json"] or "[]")
    used = [int(item) for item in json.loads(session["used_cells_json"] or "[]")]
    snapshot = json.loads(session["equipment_snapshot"] or "{}")
    tools = _interactive_dig_tools(snapshot, stage)
    resources = _snapshot_resources(snapshot)
    return {
        "id": session["id"],
        "depth": int(session["depth"]),
        "durability": int(session["durability"]),
        "maxDurability": INTERACTIVE_DIG_DURABILITY,
        "temporaryCoins": int(session["temporary_coins"]),
        "oreUnits": sum(resources.values()),
        "resources": resources,
        "merchantPrices": mine_resource_prices(),
        "luck": int(session["luck_snapshot"]),
        "mineTitle": snapshot.get("mine_title") or "Старая шахта",
        "mineEmoji": snapshot.get("mine_emoji") or "⛏",
        "routeName": snapshot.get("route_name") or "",
        "stage": stage,
        "usedCells": used,
        "tools": tools,
        "preview": stage.get("preview") if isinstance(stage, dict) else None,
    }


def _interactive_dig_tools(snapshot: dict[str, Any], stage: Any) -> list[str]:
    if isinstance(stage, dict) and stage.get("type") not in {"cells"}:
        return []
    used = set(snapshot.get("used_tools") or [])
    tools = []
    for key in ("flashlight", "map", "dynamite", "miner_hearing", "magnet", "cat_companion"):
        if int(snapshot.get(f"{key}_count", 0)) > 0 and key not in used:
            tools.append(key)
    return tools


def _interactive_cells(stage: Any) -> list[dict[str, Any]]:
    if isinstance(stage, dict):
        return list(stage.get("cells") or [])
    return list(stage or [])


def _remember_repair_candidate(snapshot: dict[str, Any], item_key: str) -> None:
    if not item_key or item_key == "repair_kit":
        return
    candidates = list(snapshot.get("repair_candidates") or [])
    candidates.append(item_key)
    snapshot["repair_candidates"] = candidates


def _repair_candidates_from_snapshot(snapshot: dict[str, Any]) -> list[str]:
    candidates = [str(item) for item in (snapshot.get("repair_candidates") or []) if item and item != "repair_kit"]
    if candidates:
        return candidates
    legacy = list(snapshot.get("used_tools") or [])
    for key in ("bucket", "flashlight", "map", "compass", "scanner", "talisman", "mystery_chest", "helmet", "shovel"):
        if snapshot.get(key) or snapshot.get(f"{key}_used"):
            legacy.append(key)
    if snapshot.get("chest") or snapshot.get("chest_used"):
        legacy.append("mystery_chest")
    return [str(item) for item in legacy if item and item != "repair_kit"]


def _item_title(game: Any, item_key: str) -> str:
    item = getattr(game, "DIG_SHOP_ITEMS", {}).get(item_key)
    if item:
        return str(item[0])
    return item_key


def _use_interactive_medkit(
    db: Database,
    game: Any,
    chat_id: int,
    user_id: int,
    snapshot: dict[str, Any],
    effects: list[str],
    text: str,
) -> bool:
    if not db.consume_dig_item(chat_id, user_id, "medkit"):
        return False
    _remember_repair_candidate(snapshot, "medkit")
    effects.append(text)
    return True


def _apply_interactive_repair_kit(
    db: Database,
    game: Any,
    chat_id: int,
    user_id: int,
    snapshot: dict[str, Any],
    effects: list[str],
) -> bool:
    candidates = _repair_candidates_from_snapshot(snapshot)
    if not candidates:
        return False
    restored = candidates[-1]
    if not snapshot.pop("repair_used", False) and not db.consume_dig_item(chat_id, user_id, "repair_kit"):
        return False
    db.add_dig_item(chat_id, user_id, restored, 1)
    effects.append(f"Ремонтный набор восстановил: {_item_title(game, restored)}")
    return True


def _db() -> Database:
    db = Database(load_config().db_path)
    db.init()
    return db


def _items_map(db: Database, user_id: int, chat_id: int = 0) -> dict[str, int]:
    return {item.item_key: item.quantity for item in db.list_dig_items(chat_id, user_id)}


def _snapshot_resources(snapshot: dict[str, Any]) -> dict[str, int]:
    resources = snapshot.get("resources")
    if isinstance(resources, dict):
        return {
            str(key): int(value)
            for key, value in resources.items()
            if key in MINE_RESOURCE_CATALOG and int(value) > 0
        }
    ore_units = int(snapshot.get("ore_units", 0) or 0)
    return {"res_iron": ore_units} if ore_units > 0 else {}


def _add_snapshot_resources(snapshot: dict[str, Any], drops: dict[str, int]) -> None:
    resources = _snapshot_resources(snapshot)
    for key, quantity in drops.items():
        if key in MINE_RESOURCE_CATALOG and int(quantity) > 0:
            resources[key] = resources.get(key, 0) + int(quantity)
    snapshot["resources"] = resources
    snapshot["ore_units"] = sum(resources.values())


def _grant_snapshot_resources(db: Database, user_id: int, snapshot: dict[str, Any], effects: list[str]) -> dict[str, int]:
    resources = _snapshot_resources(snapshot)
    if not resources:
        return {}
    for key, quantity in resources.items():
        db.add_dig_item(0, user_id, key, quantity)
    effects.append(f"Добыча сложена в сумку: {resource_stack_text(resources)}")
    snapshot["resources"] = {}
    snapshot["ore_units"] = 0
    return resources


def _gift_target_kind(game: Any, item_key: str) -> str | None:
    if item_key in game.DIG_GIFT_ITEMS:
        return "friends"
    if item_key in (game.DIG_RELATIONSHIP_ITEMS - {"couple_frame"}):
        return "partner"
    return None


def _gift_recipients(db: Database, game: Any, user_id: int, item_key: str) -> list[dict[str, Any]]:
    target_kind = _gift_target_kind(game, item_key)
    if target_kind == "friends":
        recipients = db.list_registered_social_gift_friends(user_id, limit=50)
    elif target_kind == "partner":
        recipients = db.list_registered_social_gift_partners(user_id, limit=20)
    else:
        recipients = []
    return [
        {
            "id": item.user_id,
            "username": item.username or "",
            "fullName": item.full_name,
            "relation": item.relation,
            "chatCount": item.chat_count,
        }
        for item in recipients
    ]


def _refreshed_luck(db: Database, game: Any, user_id: int, luck: int, last_luck_at: str, now: datetime) -> int:
    try:
        last = datetime.fromisoformat(last_luck_at)
    except ValueError:
        return max(0, min(100, luck))
    elapsed = max(0, (now - last).total_seconds())
    items = _items_map(db, user_id)
    multiplier = float(game.get_premium_service().get_mine_bonuses(user_id)["luck_regen_multiplier"])
    hourly_regen = game.DIG_LUCK_REGEN_PER_HOUR + game.dig_rank_bonuses(items)["luck_regen"]
    restored = int((elapsed / 3600) * hourly_regen * multiplier)
    return max(0, min(100, luck + restored))


def _dig_route(db: Database, game: Any, user_id: int) -> tuple[str, tuple[str, int, float, float, float, int]]:
    progress = db.get_dig_progress(user_id)
    key = str(progress.get("selected_route") or "old_mine")
    return (key, game.DIG_ROUTES[key]) if key in game.DIG_ROUTES else ("old_mine", game.DIG_ROUTES["old_mine"])


def _ensure_daily_contracts(db: Database, game: Any, user_id: int) -> tuple[str, list[dict]]:
    import random

    today = datetime.now(timezone.utc).date().isoformat()
    existing = db.list_dig_contracts(user_id, today)
    if not existing:
        rng = random.Random(f"{today}:{user_id}:contracts")
        keys = rng.sample(list(game.DIG_STANDARD_CONTRACTS), 3)
        db.ensure_dig_contracts(user_id, today, [(key, game.DIG_STANDARD_CONTRACTS[key][1]) for key in keys])
    return today, db.list_dig_contracts(user_id, today)


def _rank_shift_contract(db: Database, game: Any, user_id: int) -> dict | None:
    _, contracts = _ensure_daily_contracts(db, game, user_id)
    return next((item for item in contracts if item["contract_key"] in game.DIG_RANK_SHIFT_CONTRACTS), None)


def _rank_shift_public(db: Database, user_id: int, game: Any, items: dict[str, int]) -> dict[str, Any]:
    rank_name = game.dig_rank_name(items)
    if rank_name == "Новичок":
        return {
            "available": False,
            "reason": "Сменное задание открывается после покупки ранга.",
            "options": [],
            "selected": None,
        }
    selected = _rank_shift_contract(db, game, user_id)
    options = [
        {"key": key, "name": name, "target": target, "reward": reward}
        for key, (name, _, target, reward) in game.DIG_RANK_SHIFT_CONTRACTS.items()
    ]
    selected_public = None
    if selected:
        key = selected["contract_key"]
        name, _, target, reward = game.DIG_RANK_SHIFT_CONTRACTS[key]
        selected_public = {
            "key": key,
            "name": name,
            "target": int(target),
            "reward": int(reward),
            "progress": int(selected["progress"]),
            "claimed": bool(selected["claimed"]),
        }
    return {
        "available": True,
        "rank": rank_name,
        "options": options if not selected_public else [],
        "selected": selected_public,
    }


def _select_rank_shift_contract(db: Database, game: Any, user_id: int, contract_key: str) -> str | None:
    if contract_key not in game.DIG_RANK_SHIFT_CONTRACTS:
        return "Такого сменного задания нет."
    if game.dig_rank_name(_items_map(db, user_id)) == "Новичок":
        return "Сменные задания доступны после покупки ранга."
    if _rank_shift_contract(db, game, user_id):
        return "Сменное задание на сегодня уже выбрано."
    today = datetime.now(timezone.utc).date().isoformat()
    _, _, target, _ = game.DIG_RANK_SHIFT_CONTRACTS[contract_key]
    db.ensure_dig_contracts(user_id, today, [(contract_key, target)])
    return None


def _consume_star_dig(db: Database, items: dict[str, int], user_id: int, chat_id: int = 0) -> tuple[bool, bool, bool]:
    if items.get("star_depth_10", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_depth_10"):
        return True, True, True
    if items.get("star_lucky_dig", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_lucky_dig"):
        return True, True, False
    if items.get("star_dig", 0) > 0 and db.consume_dig_item(chat_id, user_id, "star_dig"):
        return True, False, False
    return False, False, False


def _update_contracts(db: Database, game: Any, user_id: int, dug: int, coins: int, artifact_found: bool) -> list[str]:
    today, _ = _ensure_daily_contracts(db, game, user_id)
    values = {"depth": dug, "coins": coins, "artifact": 1 if artifact_found else 0, "success": 1 if dug > 0 else 0}
    for key, (_, progress_key, _, _) in game.DIG_RANK_SHIFT_CONTRACTS.items():
        values[key] = values[progress_key]
    db.add_dig_contract_progress(user_id, today, values)
    claimed = db.claim_ready_dig_contracts(user_id, today)
    rewards = []
    for key in claimed:
        if key in game.DIG_RANK_SHIFT_CONTRACTS:
            reward = game.DIG_RANK_SHIFT_CONTRACTS[key][3]
            db.add_dig_coins(0, user_id, reward)
            rewards.append(f"Сменное задание «{game.DIG_CONTRACTS[key][0]}» выполнено: +{reward} котоинов")
        else:
            db.add_dig_coins(0, user_id, game.DIG_CONTRACT_REWARD_COINS)
            rewards.append(f"Контракт «{game.DIG_CONTRACTS[key][0]}» выполнен: +{game.DIG_CONTRACT_REWARD_COINS} котоинов, +{game.DIG_CONTRACT_REWARD_XP} XP")
    return rewards


def _find_artifact(db: Database, game: Any, user_id: int, depth: int, items: dict[str, int], chance_bonus: int = 0) -> tuple[int, str | None]:
    if depth <= 0 or secrets.randbelow(100) >= min(60, 5 + depth + chance_bonus):
        return 0, None
    key = list(game.DIG_ARTIFACTS)[secrets.randbelow(len(game.DIG_ARTIFACTS))]
    name = game.DIG_ARTIFACTS[key]
    if items.get(key, 0) > 0:
        bonus = 20 + depth * 3
        return bonus, f"Артефакт: снова найден «{name}». Дубликат продан за <b>{bonus}</b> котоинов."
    db.add_dig_item(0, user_id, key, 1)
    items[key] = 1
    text = f"Артефакт: найден «{name}» и добавлен в коллекцию."
    if all(items.get(artifact_key, 0) > 0 for artifact_key in game.DIG_ARTIFACTS) and items.get("artifact_set_reward", 0) <= 0:
        db.add_dig_item(0, user_id, "artifact_set_reward", 1)
        items["artifact_set_reward"] = 1
        return 250, text + " Коллекция собрана: <b>+250</b> котоинов и постоянный бонус +5% к наградам."
    return 0, text


def _award_achievement(db: Database, game: Any, user_id: int, achievement_key: str) -> str | None:
    achievement = game.DIG_ACHIEVEMENTS.get(achievement_key)
    if achievement is None:
        return None
    if not db.add_dig_achievement(0, user_id, achievement_key):
        return None
    name, _, coins, item_key = achievement
    if coins:
        db.add_dig_coins(0, user_id, coins)
    item_text = ""
    if item_key:
        db.add_dig_item(0, user_id, item_key, 1)
        item_name = game.DIG_SHOP_ITEMS.get(item_key, (item_key, 0, ""))[0]
        item_text = f", предмет: {item_name}"
    return f"{name}: +{coins} котоинов{item_text}"


def _check_achievements(db: Database, game: Any, user_id: int, player, dug: int, coins_before_reward: int, collapse_depth: int, stopped_by_stone: bool) -> list[str]:
    total_depth = player.total_depth + dug
    total_coins = player.coins + coins_before_reward
    checks = ["first_dig"]
    if dug >= 1:
        checks.append("first_meter")
    if dug >= 5:
        checks.append("five_meter_run")
    if dug >= 10:
        checks.append("ten_meter_run")
    if total_depth >= 25:
        checks.append("total_25")
    if total_depth >= 100:
        checks.append("total_100")
    if total_coins >= 500:
        checks.append("coins_500")
    if stopped_by_stone and dug == 0:
        checks.append("stone_zero")
    if collapse_depth:
        checks.append("collapse_survive")
    items = _items_map(db, user_id)
    artifact_count = sum(1 for key in game.DIG_ARTIFACTS if items.get(key, 0) > 0)
    rank = game.dig_rank_name(items)
    if rank != "Новичок" and total_depth >= 25:
        checks.append("rank_digger")
    if rank != "Новичок" and artifact_count >= 3:
        checks.append("rank_artifacts")
    if rank != "Новичок" and total_depth >= 150:
        checks.append("rank_depth")
    if items.get("rank_4", 0) > 0 and artifact_count == len(game.DIG_ARTIFACTS):
        checks.append("rank_master")
    return [text for key in checks for text in [_award_achievement(db, game, user_id, key)] if text]


def _display_name(db: Database, game: Any, user_id: int, username: str | None, full_name: str) -> str:
    name = game.dig_player_name(username, full_name)
    items = _items_map(db, user_id)
    tag = db.get_dig_player_tag(user_id)
    tag_suffix = f" «{tag}»" if tag else ""
    return f"{name}{tag_suffix}{game.dig_title_suffix(items)}"


MINIAPP_MODERATOR_ROLE_TITLES = {
    "assistant": "Помощник модератора",
    "moderator": "Модератор",
    "senior": "Старший модератор",
}
MINIAPP_MODERATOR_ROLE_RANKS = {"assistant": 1, "moderator": 2, "senior": 3}
MINIAPP_OWNER_PROFILE_ROLE = {"key": "owner", "label": "Владелец", "emoji": "👑"}
MINIAPP_ASSIGNABLE_PROFILE_ROLES = (
    {"key": "admin", "label": "Админ", "emoji": "🛡️"},
    {"key": "senior", "label": "Старший модератор", "emoji": "⭐"},
    {"key": "moderator", "label": "Модератор", "emoji": "⚖️"},
    {"key": "assistant", "label": "Помощник модера", "emoji": "🤝"},
)
MINIAPP_ASSIGNABLE_ROLE_LABELS = {str(role["label"]) for role in MINIAPP_ASSIGNABLE_PROFILE_ROLES}


def _miniapp_owner_id() -> int | None:
    return load_config().owner_id


def _miniapp_can_manage_roles(user_id: int) -> bool:
    owner_id = _miniapp_owner_id()
    return owner_id is not None and int(user_id) == int(owner_id)


def _miniapp_is_app_admin(db: Database, user_id: int) -> bool:
    if _miniapp_can_manage_roles(user_id):
        return True
    role = db.get_miniapp_profile_role(user_id)
    return bool(role and role.label == "Админ")


def _miniapp_can_view_admin_panel(db: Database, user_id: int) -> bool:
    return _miniapp_is_app_admin(db, user_id)


def _miniapp_profile_role_groups(db: Database) -> list[dict[str, Any]]:
    role_by_key = {str(role["key"]): role for role in MINIAPP_ASSIGNABLE_PROFILE_ROLES}
    all_roles = (MINIAPP_OWNER_PROFILE_ROLE, *MINIAPP_ASSIGNABLE_PROFILE_ROLES)
    by_label: dict[str, list[dict[str, Any]]] = {str(role["label"]): [] for role in all_roles}
    seen_by_label: dict[str, set[int]] = {str(role["label"]): set() for role in all_roles}

    def add(label: str, item: dict[str, Any]) -> None:
        user_id = int(item["user_id"])
        if user_id in seen_by_label.setdefault(label, set()):
            return
        seen_by_label[label].add(user_id)
        by_label.setdefault(label, []).append(item)

    owner_id = _miniapp_owner_id()
    owner_label = str(MINIAPP_OWNER_PROFILE_ROLE["label"])
    if owner_id is not None:
        known = db.get_known_user(owner_id)
        player = db.get_dig_player(0, owner_id)
        add(
            owner_label,
            {
                "user_id": int(owner_id),
                "label": owner_label,
                "username": (player.username if player else None) or (known.username if known else "") or "",
                "full_name": (player.full_name if player else None) or (known.full_name if known else str(owner_id)),
                "source": "owner",
                "canRemove": False,
                "chatCount": 0,
            },
        )

    moderator_label_by_role = {
        "senior": str(role_by_key["senior"]["label"]),
        "moderator": str(role_by_key["moderator"]["label"]),
        "assistant": str(role_by_key["assistant"]["label"]),
    }
    moderators_by_role_user: dict[tuple[str, int], dict[str, Any]] = {}
    for row in db.list_all_chat_moderators():
        role_key = str(row.get("role") or "")
        label = moderator_label_by_role.get(role_key)
        if not label:
            continue
        key = (role_key, int(row["user_id"]))
        current = moderators_by_role_user.setdefault(
            key,
            {
                **row,
                "label": label,
                "source": "moderation",
                "canRemove": True,
                "chatCount": 0,
            },
        )
        current["chatCount"] = int(current.get("chatCount") or 0) + 1
    for item in moderators_by_role_user.values():
        add(str(item["label"]), item)

    for row in db.list_miniapp_profile_roles_by_label(list(MINIAPP_ASSIGNABLE_ROLE_LABELS)):
        row["source"] = "miniapp"
        row["canRemove"] = True
        row.setdefault("chatCount", 0)
        add(str(row["label"]), row)

    return [
        {
            "key": str(role["key"]),
            "label": str(role["label"]),
            "emoji": str(role["emoji"]),
            "items": by_label.get(str(role["label"]), []),
            "assignable": role in MINIAPP_ASSIGNABLE_PROFILE_ROLES,
        }
        for role in all_roles
    ]


def _miniapp_can_view_mine_admin(db: Database, user_id: int) -> bool:
    return _miniapp_is_app_admin(db, user_id) or bool(db.list_user_moderator_roles(user_id))


def _miniapp_can_manage_mine_admin(db: Database, user_id: int) -> bool:
    return _miniapp_is_app_admin(db, user_id)


def _miniapp_can_manage_triggers(db: Database, user_id: int) -> bool:
    return _miniapp_is_app_admin(db, user_id)


def _miniapp_chat_public(chat: Any) -> dict[str, Any]:
    return {
        "id": int(chat.chat_id),
        "title": chat.title or str(chat.chat_id),
        "type": chat.type or "",
        "username": chat.username or "",
    }


def _miniapp_trigger_public(db: Database, item: Any) -> dict[str, Any]:
    variants = _miniapp_trigger_variants_public(db, item.chat_id, item.trigger)
    return {
        "chatId": int(item.chat_id),
        "trigger": item.trigger,
        "text": item.text,
        "mediaType": item.media_type or "",
        "hasMedia": bool(item.media_type and item.media_file_id),
        "updatedAt": item.updated_at,
        "variants": variants,
    }


def _miniapp_trigger_variant_public(item: Any) -> dict[str, Any]:
    media_type = getattr(item, "media_type", None) or ""
    variant_type = getattr(item, "variant_type", None) or media_type or "text"
    return {
        "id": int(getattr(item, "id", 0) or 0),
        "chatId": int(item.chat_id),
        "trigger": item.trigger,
        "variantType": variant_type,
        "text": getattr(item, "text", "") or "",
        "mediaType": media_type,
        "mediaFileId": getattr(item, "media_file_id", None) or "",
        "hasMedia": bool(getattr(item, "media_type", None) and getattr(item, "media_file_id", None)),
    }


def _miniapp_trigger_variants_public(db: Database, chat_id: int, trigger: str) -> list[dict[str, Any]]:
    variants = db.list_trigger_variants(chat_id, trigger)
    if variants:
        return [_miniapp_trigger_variant_public(item) for item in variants]
    item = next((row for row in db.list_triggers(chat_id) if row.trigger == normalize_trigger(trigger)), None)
    return [_miniapp_trigger_variant_public(item)] if item else []


def _trigger_media_dir() -> Path:
    root = Path(load_config().db_path).resolve().parent / "trigger_media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_trigger_variants(payload: MiniAppTriggerSave) -> list[dict[str, object]]:
    raw_variants: list[MiniAppTriggerVariant] = list(payload.variants)
    if not raw_variants and payload.text is not None:
        raw_variants = [MiniAppTriggerVariant(variantType="text", text=payload.text)]
    cleaned: list[dict[str, object]] = []
    text_count = 0
    media_seen: set[str] = set()
    for item in raw_variants:
        variant_type = (item.variantType or "text").strip().casefold()
        if variant_type == "gif":
            variant_type = "animation"
        if variant_type not in {"text", "photo", "animation", "audio"}:
            raise HTTPException(400, "Неизвестный тип ответа триггера.")
        text = (item.text or "").strip()
        media_type = (item.mediaType or "").strip() or None
        media_file_id = (item.mediaFileId or "").strip() or None
        if variant_type == "text":
            text_count += 1
            if text_count > 10:
                raise HTTPException(400, "На один триггер можно добавить максимум 10 текстовых ответов.")
            if not text:
                continue
            media_type = None
            media_file_id = None
        else:
            if variant_type in media_seen:
                raise HTTPException(400, "Для каждого типа медиа можно сохранить один вариант.")
            media_seen.add(variant_type)
            if not media_file_id:
                continue
            media_type = media_type or variant_type
        cleaned.append(
            {
                "variant_type": variant_type,
                "text": text,
                "media_type": media_type,
                "media_file_id": media_file_id,
            }
        )
    if not cleaned:
        raise HTTPException(400, "Добавь хотя бы один ответ для триггера.")
    return cleaned


def _miniapp_dig_player_public(db: Database, player: Any) -> dict[str, Any]:
    item_keys = ("star_dig", "golden_ticket", "super_game_pass")
    return {
        "chat_id": player.chat_id,
        "user_id": player.user_id,
        "username": player.username or "",
        "full_name": player.full_name,
        "coins": player.coins,
        "total_depth": player.total_depth,
        "best_session_depth": player.best_session_depth,
        "luck": player.luck,
        "last_dig_at": player.last_dig_at,
        "updated_at": player.updated_at,
        "extraDigs": db.get_dig_item_quantity(0, player.user_id, "star_dig"),
        "goldenTickets": db.get_dig_item_quantity(0, player.user_id, "golden_ticket"),
        "superPasses": db.get_dig_item_quantity(0, player.user_id, "super_game_pass"),
        "specialItems": {
            key: db.get_dig_item_quantity(0, player.user_id, key)
            for key in item_keys
        },
    }


def _miniapp_dig_block_public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": int(item["user_id"]),
        "username": item.get("username") or "",
        "full_name": item.get("full_name") or str(item["user_id"]),
        "reason": item.get("reason") or "",
        "blocked_by": item.get("blocked_by"),
        "created_at": item.get("created_at") or "",
    }


def _ensure_mine_not_blocked(db: Database, user_id: int) -> None:
    block = db.get_dig_block(user_id)
    if block:
        reason = str(block.get("reason") or "").strip()
        detail = "Доступ к шахте заблокирован."
        if reason:
            detail += f" Причина: {reason}"
        raise HTTPException(403, detail)


def _normalize_profile_role_label(label: str) -> str:
    normalized = " ".join(label.strip().split())
    if not normalized:
        raise HTTPException(400, "Укажи текст роли.")
    if len(normalized) > 16:
        raise HTTPException(400, "Роль должна быть до 16 символов.")
    if normalized not in MINIAPP_ASSIGNABLE_ROLE_LABELS:
        raise HTTPException(400, "Можно выбрать только одну из доступных ролей приложения.")
    return normalized


def _resolve_profile_role_target(db: Database, target: str) -> tuple[int, str, str | None]:
    value = target.strip()
    if not value:
        raise HTTPException(400, "Укажи ID или @username пользователя.")
    if value.startswith("@"):
        user = db.get_known_user_by_username(value[1:])
        if not user:
            raise HTTPException(404, "Я ещё не видел пользователя с таким @username.")
        return user.user_id, user.full_name, user.username
    if value.isdigit():
        user_id = int(value)
        known = db.get_known_user(user_id)
        player = db.get_dig_player(0, user_id)
        if player:
            return user_id, player.full_name, player.username
        if known:
            return user_id, known.full_name, known.username
        return user_id, str(user_id), None
    raise HTTPException(400, "Цель должна быть ID или @username.")


def _miniapp_profile_roles(db: Database, user_id: int) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    owner_id = _miniapp_owner_id()
    if owner_id is not None and int(user_id) == int(owner_id):
        roles.append({"key": "owner", "title": "Владелец", "kind": "owner", "emoji": "👑"})

    custom = db.get_miniapp_profile_role(user_id)
    if custom:
        predefined = next((role for role in MINIAPP_ASSIGNABLE_PROFILE_ROLES if str(role["label"]) == custom.label), None)
        role_key = str(predefined["key"]) if predefined else "custom"
        roles.append(
            {
                "key": role_key,
                "title": custom.label,
                "kind": "admin" if custom.label == "Админ" else "custom",
                "emoji": custom.emoji or (str(predefined["emoji"]) if predefined else "🏷️"),
                "color": custom.color or "",
            }
        )

    moderator_roles = db.list_user_moderator_roles(user_id)
    if moderator_roles:
        best = max(
            moderator_roles,
            key=lambda row: MINIAPP_MODERATOR_ROLE_RANKS.get(str(row["role"]), 0),
        )
        role_key = str(best["role"])
        roles.append(
            {
                "key": f"moderation:{role_key}",
                "title": MINIAPP_MODERATOR_ROLE_TITLES.get(role_key, "Модерация"),
                "kind": "moderation",
                "emoji": "⚖️",
                "chatCount": len({int(row["chat_id"]) for row in moderator_roles}),
            }
        )
    return roles


def _telegram_user(init_data: str | None) -> dict[str, Any]:
    if not init_data:
        raise HTTPException(401, "Откройте игру через Telegram.")
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    supplied_hash = values.pop("hash", "")
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", load_config().bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not supplied_hash or not hmac.compare_digest(expected, supplied_hash):
        raise HTTPException(401, "Подпись Telegram недействительна.")
    try:
        if datetime.now(timezone.utc).timestamp() - int(values["auth_date"]) > 86400:
            raise ValueError
        tg_user = json.loads(values["user"])
        return {
            "id": int(tg_user["id"]),
            "username": tg_user.get("username"),
            "full_name": " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or str(tg_user["id"]),
            "photo_url": tg_user.get("photo_url") or "",
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Данные пользователя Telegram устарели.") from exc


def _miniapp_avatar_dir() -> str:
    project_root = Path(__file__).resolve().parent.parent
    return os.getenv("USER_AVATAR_DIR", str(project_root / "media_storage" / "user_avatars")).strip()


def _miniapp_avatar_path(user_id: int) -> str:
    return os.path.join(_miniapp_avatar_dir(), f"{user_id}.jpg")


def _miniapp_avatar_signature(user_id: int) -> str:
    return hmac.new(
        load_config().bot_token.encode(),
        f"miniapp-avatar:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _miniapp_avatar_url(user_id: int) -> str:
    return f"/miniapp/avatar/{user_id}?sig={_miniapp_avatar_signature(user_id)}"


def _valid_miniapp_avatar_signature(user_id: int, signature: str) -> bool:
    return bool(signature) and hmac.compare_digest(_miniapp_avatar_signature(user_id), signature)


async def _ensure_miniapp_avatar(user_id: int) -> str | None:
    path = _miniapp_avatar_path(user_id)
    max_age_seconds = 24 * 60 * 60
    if os.path.exists(path) and (datetime.now().timestamp() - os.path.getmtime(path)) < max_age_seconds:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    bot = Bot(token=load_config().bot_token)
    tmp_path = f"{path}.tmp"
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos.photos:
            return path if os.path.exists(path) else None
        largest = max(photos.photos[0], key=lambda item: item.file_size or 0)
        file = await bot.get_file(largest.file_id)
        if not file.file_path:
            return path if os.path.exists(path) else None
        await bot.download_file(file.file_path, destination=tmp_path)
        os.replace(tmp_path, path)
        return path
    except Exception:
        return path if os.path.exists(path) else None
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        await bot.session.close()


def _miniapp_social_people(db: Database, viewer_id: int) -> list[dict[str, Any]]:
    people: dict[int, dict[str, Any]] = {}
    for item in db.list_social_friends(viewer_id, limit=80):
        people[item.user_id] = {
            "id": item.user_id,
            "username": item.username or "",
            "fullName": item.full_name,
            "relation": "friend",
            "relationTitle": "Друг",
            "chatCount": item.chat_count,
            "photoUrl": _miniapp_avatar_url(item.user_id),
        }
    for item in db.list_social_partners(viewer_id, limit=20):
        people[item.user_id] = {
            "id": item.user_id,
            "username": item.username or "",
            "fullName": item.full_name,
            "relation": "partner",
            "relationTitle": "Пара",
            "chatCount": item.chat_count,
            "photoUrl": _miniapp_avatar_url(item.user_id),
        }
    return sorted(people.values(), key=lambda item: (item["relation"] != "partner", item["fullName"].lower()))


def _miniapp_social_target(db: Database, viewer_id: int, target_id: int) -> dict[str, Any] | None:
    if target_id == viewer_id:
        return {"relation": "self", "relationTitle": ""}
    for item in _miniapp_social_people(db, viewer_id):
        if int(item["id"]) == target_id:
            return item
    return None


def _radio_stream_token(url: str) -> str:
    payload = {
        "url": url,
        "exp": int(time.time()) + 30 * 24 * 60 * 60,
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    secret = load_config().bot_token.encode()
    signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{signature}"


def _radio_stream_url(token: str) -> str:
    try:
        body, signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise HTTPException(400, "Ссылка радиопотока устарела.") from exc
    secret = load_config().bot_token.encode()
    expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Подпись радиопотока неверна.")
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Ссылка радиопотока повреждена.") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(410, "Ссылка радиопотока устарела. Найди станцию заново.")
    url = str(payload.get("url") or "")
    if not url:
        raise HTTPException(400, "В ссылке радиопотока нет адреса.")
    return url


def _radio_station_public(station: dict[str, Any]) -> dict[str, Any]:
    url = str(station.get("url_resolved") or station.get("url") or "")
    uuid = str(station.get("stationuuid") or station.get("uuid") or "")
    result = {
        "name": str(station.get("name") or "Без названия"),
        "stationuuid": uuid,
        "url": url,
        "url_resolved": url,
        "favicon": str(station.get("favicon") or ""),
        "country": str(station.get("country") or ""),
        "tags": str(station.get("tags") or ""),
        "bitrate": station.get("bitrate"),
        "codec": str(station.get("codec") or ""),
        "homepage": str(station.get("homepage") or ""),
    }
    if url:
        result["streamUrl"] = f"/miniapp/radio/stream?token={_radio_stream_token(url)}"
    return result


def _state(db: Database, user_id: int) -> dict[str, Any]:
    from . import bot as game
    _ensure_mine_not_blocked(db, user_id)
    player = db.get_dig_player(0, user_id)
    if not player:
        return {"registered": False, "userId": user_id}
    session = db.get_dig_session(user_id)
    interactive_session = _interactive_dig_public(db, user_id)
    now = datetime.now(timezone.utc)
    cooldown = None
    if player.last_dig_at and not session and not interactive_session:
        cooldown_at = datetime.fromisoformat(player.last_dig_at) + game.user_dig_cooldown(user_id)
        if cooldown_at > now:
            cooldown = cooldown_at.isoformat()
    progress = db.get_dig_progress(user_id)
    items = {x.item_key: x.quantity for x in db.list_dig_items(0, user_id)}
    rank_key = next((key for key, _ in game.DIG_RANKS if items.get(key, 0) > 0), None)
    rank_level = {"rank_1": 1, "rank_2": 2, "rank_3": 3, "rank_4": 4}.get(rank_key, 0)
    return {"registered": True, "userId": user_id,
            "name": _display_name(db, game, player.user_id, player.username, player.full_name),
            "coins": player.coins,
            "luck": _refreshed_luck(db, game, user_id, player.luck, player.last_luck_at, now),
            "totalDepth": player.total_depth, "record": player.best_session_depth,
            "level": progress["level"], "xp": progress["xp"], "streak": progress["streak"],
            "sessionDepth": int(interactive_session["depth"]) if interactive_session else int(session["depth"]) if session else 0,
            "inSession": bool(session or interactive_session),
            "interactiveMine": interactive_session,
            "cooldownUntil": cooldown,
            "items": items,
            "rank": {"key": rank_key, "name": game.dig_rank_name(items), "level": rank_level},
            "rankShift": _rank_shift_public(db, user_id, game, items),
            "goldenTickets": db.get_dig_item_quantity(0, user_id, "golden_ticket"),
            "ticketGame": _ticket_public(db, user_id),
            "superPasses": db.get_dig_item_quantity(0, user_id, "super_game_pass"),
            "superGame": _super_ticket_public(db, user_id),
            "superRewards": {
                "mute30": db.get_dig_item_quantity(0, user_id, "super_mute30"),
                "tag": db.get_dig_item_quantity(0, user_id, "super_tag"),
            }}


def _begin_manual(db: Database, game: Any, user: dict[str, Any], now: datetime) -> None:
    uid = user["id"]
    _ensure_mine_not_blocked(db, uid)
    player = db.get_dig_player(0, uid)
    if not player:
        raise HTTPException(400, "Сначала зарегистрируйтесь в игре.")
    if db.get_active_interactive_dig_session(uid):
        raise HTTPException(400, "У тебя уже идет ручная вылазка. Заверши ее перед автоматической раскопкой.")

    items = _items_map(db, uid)
    star_dig_used, forced_luck, forced_depth = _consume_star_dig(db, items, uid)
    camp_used = False
    if player.last_dig_at and not star_dig_used:
        last_dig = datetime.fromisoformat(player.last_dig_at)
        cooldown = game.user_dig_cooldown(uid)
        next_dig = last_dig + cooldown
        if now < next_dig and items.get("camp", 0) > 0 and now >= last_dig + cooldown / 2:
            camp_used = db.consume_dig_item(0, uid, "camp")
            if camp_used:
                next_dig = now
        if now < next_dig:
            left = max(1, int((next_dig - now).total_seconds()))
            raise HTTPException(429, f"Кирка отдыхает еще {left // 3600} ч {(left % 3600) // 60} мин.")

    route_key, route = _dig_route(db, game, uid)
    route_name, route_chance, route_coins, route_artifacts, route_collapse, _ = route
    luck = _refreshed_luck(db, game, uid, player.luck, player.last_luck_at, now)
    if luck < game.DIG_LUCK_COST and not forced_luck:
        raise HTTPException(400, f"Недостаточно удачи: нужно {game.DIG_LUCK_COST}, сейчас {luck}.")

    helmet = not forced_luck and items.get("helmet", 0) > 0 and db.consume_dig_item(0, uid, "helmet")
    shovel = not forced_luck and items.get("shovel", 0) > 0 and db.consume_dig_item(0, uid, "shovel")
    flashlight = not forced_depth and items.get("flashlight", 0) > 0 and db.consume_dig_item(0, uid, "flashlight")
    bucket = items.get("bucket", 0) > 0 and db.consume_dig_item(0, uid, "bucket")
    compass = items.get("compass", 0) > 0 and db.consume_dig_item(0, uid, "compass")
    scanner = items.get("scanner", 0) > 0 and db.consume_dig_item(0, uid, "scanner")
    map_used = items.get("map", 0) > 0 and db.consume_dig_item(0, uid, "map")
    talisman = items.get("talisman", 0) > 0 and db.consume_dig_item(0, uid, "talisman")
    repair = items.get("repair_kit", 0) > 0
    chest = items.get("mystery_chest", 0) > 0 and db.consume_dig_item(0, uid, "mystery_chest")

    if compass:
        route_chance = round(route_chance * 1.25)
        route_coins *= 1.15

    shovel_bonus = game.dig_permanent_shovel_bonus(items)
    cart_bonus = game.dig_cart_bonus(items)
    backpack_bonus = game.dig_backpack_bonus(items)
    helmet_reduction = game.dig_helmet_reduction(items)
    artifact_equipment_bonus = game.dig_flashlight_artifact_bonus(items)
    rank_bonuses = game.dig_rank_bonuses(items)
    collection_bonus = items.get("artifact_set_reward", 0) > 0
    effective_luck = 100 if forced_luck else min(100, luck + (5 if helmet else 0))

    effects: list[str] = [f"Маршрут: {route_name}"]
    for used, text in (
        (camp_used, "Переносной лагерь: ожидание сокращено"),
        (star_dig_used, "Оплаченная раскопка: ожидание пропущено"),
        (forced_luck, "Оплаченная раскопка: действует 100 удачи"),
        (forced_depth, "Оплаченная раскопка: гарантированные 10 м"),
        (helmet, "Каска шахтера: +5 удачи"),
        (shovel, "Крепкая кирка: риск обвала снижен"),
        (flashlight, "Фонарик: +10% к шансу метра"),
        (bucket, "Премиум ведро: +25% котоинов"),
        (compass, "Компас: маршрут усилен"),
        (scanner, "Сканер породы: риск обвала -30%"),
        (map_used, "Карта тоннелей: +15% к артефактам"),
        (talisman, "Талисман: котоины будут удвоены"),
        (chest, "Таинственный сундук активирован"),
        (collection_bonus, "Коллекция артефактов: +5% котоинов"),
    ):
        if used:
            effects.append(text)
    if shovel_bonus:
        effects.append(f"Постоянная кирка: +{shovel_bonus}% к шансам")
    if cart_bonus:
        effects.append(f"Вагонетка: +{cart_bonus}% котоинов")
    if backpack_bonus:
        effects.append(f"Рюкзак: +{backpack_bonus}% котоинов")
    if helmet_reduction:
        effects.append(f"Каска: риск обвала -{helmet_reduction}%")
    if artifact_equipment_bonus:
        effects.append(f"Фонарь: +{artifact_equipment_bonus}% к артефактам")
    if rank_bonuses["chance"]:
        effects.append(f"Ранг: +{rank_bonuses['chance']}% к шансам метров")

    data = {
        "routeName": route_name,
        "routeChance": route_chance,
        "routeCoins": route_coins,
        "routeArtifacts": route_artifacts,
        "routeCollapse": route_collapse,
        "luckForChance": effective_luck,
        "luckAfter": luck if forced_luck else luck - game.DIG_LUCK_COST,
        "helmet": helmet,
        "shovel": shovel,
        "flashlight": flashlight,
        "bucket": bucket,
        "compass": compass,
        "scanner": scanner,
        "map": map_used,
        "talisman": talisman,
        "repair": repair,
        "chest": chest,
        "forcedDepth": forced_depth,
        "shovelBonus": shovel_bonus,
        "cartBonus": cart_bonus,
        "backpackBonus": backpack_bonus,
        "helmetReduction": helmet_reduction,
        "artifactBonus": artifact_equipment_bonus,
        "collectionBonus": collection_bonus,
        "rankCoins": rank_bonuses["coins"],
        "rankChance": rank_bonuses["chance"],
    }
    text = now.isoformat(timespec="seconds")
    db.set_dig_luck(0, uid, data["luckAfter"], text)
    db.save_dig_session(uid, 0, luck, route_key, json.dumps(data), json.dumps(effects), text)


def _begin_interactive_manual(db: Database, game: Any, user: dict[str, Any], now: datetime) -> dict[str, Any]:
    uid = user["id"]
    _ensure_mine_not_blocked(db, uid)
    player = db.get_dig_player(0, uid)
    if not player:
        raise HTTPException(400, "Сначала зарегистрируйтесь в игре.")
    if db.get_dig_session(uid):
        db.clear_dig_session(uid)
    active = db.get_active_interactive_dig_session(uid)
    if active:
        return active

    items = _items_map(db, uid)
    star_dig_used, forced_luck, forced_depth = _consume_star_dig(db, items, uid)

    camp_used = False
    if player.last_dig_at and not star_dig_used:
        last_dig = datetime.fromisoformat(player.last_dig_at)
        cooldown = game.user_dig_cooldown(uid)
        next_dig = last_dig + cooldown
        if now < next_dig and items.get("camp", 0) > 0 and now >= last_dig + cooldown / 2:
            camp_used = db.consume_dig_item(0, uid, "camp")
            if camp_used:
                next_dig = now
        if now < next_dig:
            left = max(1, int((next_dig - now).total_seconds()))
            raise HTTPException(429, f"Кирка отдыхает еще {left // 3600} ч {(left % 3600) // 60} мин.")

    route_key, route = _dig_route(db, game, uid)
    route_name, route_chance, route_coins, route_artifacts, route_collapse, _ = route
    mine = mine_type_for_total_depth(player.total_depth)
    luck = _refreshed_luck(db, game, uid, player.luck, player.last_luck_at, now)
    if luck < game.DIG_LUCK_COST and not forced_luck and not forced_depth:
        raise HTTPException(400, f"Недостаточно удачи: нужно {game.DIG_LUCK_COST}, сейчас {luck}.")

    helmet = not forced_luck and items.get("helmet", 0) > 0 and db.consume_dig_item(0, uid, "helmet")
    shovel = not forced_luck and items.get("shovel", 0) > 0 and db.consume_dig_item(0, uid, "shovel")
    bucket = items.get("bucket", 0) > 0 and db.consume_dig_item(0, uid, "bucket")
    compass = items.get("compass", 0) > 0 and db.consume_dig_item(0, uid, "compass")
    scanner = items.get("scanner", 0) > 0 and db.consume_dig_item(0, uid, "scanner")
    talisman = items.get("talisman", 0) > 0 and db.consume_dig_item(0, uid, "talisman")
    chest = items.get("mystery_chest", 0) > 0 and db.consume_dig_item(0, uid, "mystery_chest")
    repair_candidates = [
        key
        for key, used in (
            ("helmet", helmet),
            ("shovel", shovel),
            ("bucket", bucket),
            ("compass", compass),
            ("scanner", scanner),
            ("talisman", talisman),
            ("mystery_chest", chest),
        )
        if used
    ]

    if compass:
        route_chance = round(route_chance * 1.25)
        route_coins *= 1.15
    route_coins *= (100 + int(mine.get("reward_bonus", 0))) / 100
    shovel_bonus = game.dig_permanent_shovel_bonus(items)
    cart_bonus = game.dig_cart_bonus(items)
    backpack_bonus = game.dig_backpack_bonus(items)
    helmet_reduction = game.dig_helmet_reduction(items)
    rank_bonuses = game.dig_rank_bonuses(items)
    collection_bonus = items.get("artifact_set_reward", 0) > 0
    premium_multiplier = float(game.get_premium_service().get_mine_bonuses(uid)["coins_multiplier"])
    premium_bonus = max(0, round((premium_multiplier - 1) * 100))
    coin_bonus_percent = (25 if bucket else 0) + cart_bonus + backpack_bonus + (5 if collection_bonus else 0) + rank_bonuses["coins"] + premium_bonus
    chance_bonus = route_chance + float(mine.get("chance_bonus", 0.0)) + shovel_bonus + rank_bonuses["chance"]
    loss_protection = (15 if shovel else 0) + (5 if scanner else 0) + helmet_reduction // 3
    effects = [f"Маршрут: {route_name}"]
    if camp_used:
        effects.append("Лагерь: ожидание сокращено")
    if star_dig_used:
        effects.append("Оплаченная раскопка: ожидание пропущено" + (" и действует 100 удачи" if forced_luck else ""))

    snapshot = {
        "route_name": route_name,
        "route_chance": route_chance,
        "route_coins": route_coins,
        "route_artifacts": route_artifacts,
        "route_collapse": route_collapse,
        "mine_key": mine["key"],
        "mine_title": mine["title"],
        "mine_emoji": mine["emoji"],
        "luck_before": luck,
        "luck_after": luck if forced_luck else luck - game.DIG_LUCK_COST,
        "chance_bonus": chance_bonus,
        "coin_bonus_percent": coin_bonus_percent,
        "loss_protection": loss_protection,
        "map_used": False,
        "talisman_used": talisman,
        "chest_used": chest,
        "insurance_count": int(items.get("insurance", 0)),
        "flashlight_count": int(items.get("flashlight", 0)),
        "map_count": int(items.get("map", 0)),
        "dynamite_count": int(items.get("dynamite", 0)),
        "miner_hearing_count": int(items.get("miner_hearing", 0)),
        "magnet_count": int(items.get("magnet", 0)),
        "cat_companion_count": int(items.get("cat_companion", 0)),
        "ore_units": 0,
        "resources": {},
        "used_tools": [],
        "repair_candidates": repair_candidates,
        "used_effects": effects,
    }
    db.set_dig_luck(0, uid, int(snapshot["luck_after"]), now.isoformat(timespec="seconds"))
    initial_depth = INTERACTIVE_DIG_MAX_DEPTH - 1 if forced_depth else 0
    initial_stage = generate_dig_stage(INTERACTIVE_DIG_MAX_DEPTH, str(mine["key"])) if forced_depth else generate_dig_stage(1, str(mine["key"]))
    return db.create_interactive_dig_session(
        session_id=secrets.token_hex(8),
        user_id=uid,
        chat_id=0,
        route_key=route_key,
        depth=initial_depth,
        durability=INTERACTIVE_DIG_DURABILITY,
        temporary_coins=0,
        luck_snapshot=100 if forced_luck else luck,
        equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
        cells_json=json.dumps(initial_stage, ensure_ascii=False),
    )


def _finish_manual(db: Database, game: Any, user: dict[str, Any], session: dict[str, Any], depth: int, now: datetime) -> str:
    uid = user["id"]
    player_before = db.get_dig_player(0, uid)
    data = json.loads(session["route_data"])
    effects = json.loads(session["used_effects"] or "[]")
    items = _items_map(db, uid)

    collapse = max(0, int(max(0, 100 - data["luckForChance"]) * data["routeCollapse"]))
    collapse = max(0, collapse - int(data.get("helmetReduction", 0)))
    if data.get("scanner"):
        collapse = collapse * 70 // 100
    if data.get("shovel"):
        collapse //= 2

    lost = 0
    if depth and collapse and secrets.randbelow(100) < collapse:
        if db.consume_dig_item(0, uid, "safe"):
            effects.append("Сейф: обвал остановлен")
        else:
            lost = 1 + secrets.randbelow(depth)
            depth = max(0, depth - lost)

    coins = max(1, int(game.dig_coin_reward(depth) * data["routeCoins"] + 0.9999))
    if data.get("bucket"):
        coins = (coins * 125 + 99) // 100
    if data.get("cartBonus"):
        coins = (coins * (100 + int(data["cartBonus"])) + 99) // 100
    if data.get("backpackBonus"):
        coins = (coins * (100 + int(data["backpackBonus"])) + 99) // 100
    if data.get("collectionBonus"):
        coins = (coins * 105 + 99) // 100

    coins = game.scale_auto_dig_reward(coins)
    event = None
    effects.append("Автоматический режим: добыча снижена, ручных событий и руды нет")

    artifact_chance_bonus = (
        max(0, int((data["routeArtifacts"] - 1) * 10))
        + int(data.get("artifactBonus", 0))
        + (15 if data.get("map") else 0)
    )
    artifact_coins, artifact = _find_artifact(db, game, uid, depth, items, artifact_chance_bonus)
    coins += artifact_coins

    if data.get("talisman"):
        coins *= 2
        effects.append("Талисман: котоины удвоены")

    if data.get("chest"):
        chest_roll = secrets.randbelow(4)
        if chest_roll == 0:
            effects.append("Таинственный сундук оказался пуст")
        elif chest_roll == 1:
            bonus = 25 + secrets.randbelow(51)
            coins += bonus
            effects.append(f"Таинственный сундук: +{bonus} котоинов")
        elif chest_roll == 2:
            db.add_dig_item(0, uid, "insurance", 1)
            effects.append("Таинственный сундук: найдена страховка")
        else:
            db.add_dig_item(0, uid, "dynamite", 1)
            effects.append("Таинственный сундук: найден динамит")

    if data.get("rankCoins"):
        coins = (coins * (100 + int(data["rankCoins"])) + 99) // 100
        effects.append(f"Ранг: +{int(data['rankCoins'])}% котоинов")

    if data.get("repair"):
        restored = (
            "bucket" if data.get("bucket") else
            "flashlight" if data.get("flashlight") else
            "map" if data.get("map") else
            "compass" if data.get("compass") else
            "scanner" if data.get("scanner") else
            "talisman" if data.get("talisman") else
            "mystery_chest" if data.get("chest") else
            "helmet" if data.get("helmet") else
            "shovel" if data.get("shovel") else
            None
        )
        if restored and db.consume_dig_item(0, uid, "repair_kit"):
            db.add_dig_item(0, uid, restored, 1)
            effects.append(f"Ремонтный набор восстановил: {game.DIG_SHOP_ITEMS[restored][0]}")

    coins = game.apply_premium_coin_bonus(uid, coins, effects)
    text = now.isoformat(timespec="seconds")
    db.update_dig_player_after_dig(0, uid, user.get("username"), user["full_name"], coins, depth, depth, data["luckAfter"], text, text)
    db.add_dig_weekly_depth(uid, game.dig_week_start(now), depth)
    contract_updates = _update_contracts(db, game, uid, depth, coins, artifact is not None)
    progress = db.update_dig_progress(
        uid,
        5 + depth * 10 + game.dig_contract_xp_reward(contract_updates),
        depth > 0,
        session["route_key"],
    )
    achievement_updates = _check_achievements(db, game, uid, player_before, depth, coins, lost, depth == 0)

    expedition = db.add_dig_expedition_progress(0, uid, now.date().isoformat(), depth, game.DIG_EXPEDITION_TARGET)
    if expedition["completed"]:
        db.reward_dig_expedition(0, now.date().isoformat(), game.DIG_EXPEDITION_REWARD)
        effects.append(f"Экспедиция завершена: +{game.DIG_EXPEDITION_REWARD} котоинов")

    ticket_found = game.find_golden_ticket(depth)
    if ticket_found:
        db.add_dig_item(0, uid, "golden_ticket", 1)
        effects.append("Золотой билет найден")

    db.clear_dig_session(uid)
    lines = [f"Вылазка завершена: {depth} м", f"+{coins} котоинов", f"Уровень {progress['level']}, XP {progress['xp']}"]
    if lost:
        lines.append(f"Обвал забрал {lost} м")
    if event:
        lines.append(event)
    if artifact:
        lines.append(artifact)
    lines.extend(contract_updates)
    if achievement_updates:
        lines.append("")
        lines.append("Достижения:")
        lines.extend(f"• {item}" for item in achievement_updates)
    if effects:
        lines.append("")
        lines.append("Сработало:")
        lines.extend(f"• {item}" for item in effects)
    return "\n".join(lines)


@router.get("/miniapp", response_class=HTMLResponse)
def miniapp_page() -> HTMLResponse:
    return HTMLResponse(
        MINI_APP_UI_HTML,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/miniapp/shop-bg.png")
def miniapp_shop_background() -> FileResponse:
    return FileResponse(Path(__file__).with_name("shop-bg.png"), media_type="image/png")


def _shop_catalog(db: Database, user_id: int) -> dict[str, Any]:
    from . import bot as game

    items = {item.item_key: item.quantity for item in db.list_dig_items(0, user_id)}
    categories: list[dict[str, Any]] = []
    for category_key in game.DIG_SHOP_CATEGORY_ORDER:
        title, item_keys = game.DIG_SHOP_CATEGORIES[category_key]
        products: list[dict[str, Any]] = []
        for item_key in item_keys:
            if item_key == "prank":
                # This item sends a message to a selected group and remains a chat-only action.
                continue
            item = game.DIG_SHOP_ITEMS.get(item_key)
            if not item:
                continue
            name, base_price, description = item
            price = game.dig_shop_price(item_key, items)
            discount = game.dig_rank_discount(items) if item_key in game.dig_discountable_item_keys() else 0
            products.append(
                {
                    "key": item_key,
                    "name": name,
                    "price": price,
                    "basePrice": base_price,
                    "discount": discount,
                    "description": description,
                    "quantity": items.get(item_key, 0),
                    "owned": item_key in game.DIG_PERMANENT_ITEMS and items.get(item_key, 0) > 0,
                    "requirement": game.DIG_ITEM_REQUIREMENTS.get(item_key),
                    "requirementName": (
                        game.DIG_SHOP_ITEMS[game.DIG_ITEM_REQUIREMENTS[item_key]][0]
                        if item_key in game.DIG_ITEM_REQUIREMENTS
                        else None
                    ),
                    "canBuy": not game.dig_purchase_error(items, item_key),
                }
            )
        if products:
            categories.append({"key": category_key, "title": title, "items": products})

    star_products: list[dict[str, Any]] = []
    for action, (title, description, star_price, item_key, quantity) in game.DIG_STAR_ACTIONS.items():
        current_quantity = db.get_dig_item_quantity(0, user_id, item_key) if item_key else 0
        star_products.append(
            {
                "key": action,
                "name": title,
                "price": 0,
                "basePrice": 0,
                "starPrice": star_price,
                "discount": 0,
                "description": description,
                "quantity": current_quantity,
                "owned": False,
                "requirement": None,
                "requirementName": None,
                "canBuy": True,
                "instant": item_key is None,
                "grantItem": item_key,
                "grantQuantity": quantity,
            }
        )
    categories.append(
        {
            "key": "stars",
            "title": "Покупки за Stars",
            "items": star_products,
        }
    )

    names = {key: value[0] for key, value in game.DIG_SHOP_ITEMS.items()}
    names.update(game.DIG_ARTIFACTS)
    names.update({key: str(value["title"]) for key, value in MINE_RESOURCE_CATALOG.items()})
    names.update(
        {
            "artifact_set_reward": "Бонус полной коллекции",
            "super_game_pass": "Доступ к супер-игре 9×9",
            "super_mute30": "Право на мут 30 минут",
            "super_tag": "Право выбрать тег",
        }
    )
    paid_keys = {"star_dig", "star_lucky_dig", "star_depth_10", "super_game_pass", "super_mute30", "super_tag"}
    artifact_keys = set(game.DIG_ARTIFACTS) | {"artifact_set_reward"}
    chain_keys = {key for chain in game.DIG_SHOP_UPGRADE_CHAINS for key in chain}
    best_chain_keys = {
        owned_key
        for chain in game.DIG_SHOP_UPGRADE_CHAINS
        for owned_key in [next((key for key in reversed(chain) if items.get(key, 0) > 0), "")]
        if owned_key
    }
    supply_keys = set(game.DIG_SHOP_CATEGORIES["consumables"][1]) | set(game.DIG_SHOP_CATEGORIES["gear"][1]) | {
        "golden_ticket"
    }
    supply_keys |= game.DIG_GIFT_ITEMS | game.DIG_RELATIONSHIP_ITEMS
    grouped: dict[str, list[dict[str, Any]]] = {
        "Коллекция": [],
        "Добыча": [],
        "Постоянные улучшения": [],
        "Припасы и билеты": [],
        "Особые награды": [],
    }
    for key, quantity in items.items():
        if quantity <= 0 or key not in names:
            continue
        if key == "title_badge":
            continue
        if key in chain_keys and key not in best_chain_keys:
            continue
        entry = {
            "key": key,
            "name": names[key],
            "quantity": quantity,
            "giftable": _gift_target_kind(game, key) is not None,
            "giftTargetKind": _gift_target_kind(game, key),
        }
        if key in artifact_keys:
            grouped["Коллекция"].append(entry)
        elif key in MINE_RESOURCE_CATALOG:
            grouped["Добыча"].append(entry)
        elif key in game.DIG_PERMANENT_ITEMS:
            grouped["Постоянные улучшения"].append(entry)
        elif key in supply_keys:
            grouped["Припасы и билеты"].append(entry)
        elif key in paid_keys:
            grouped["Особые награды"].append(entry)

    icons = {
        "Коллекция": "💎",
        "Добыча": "⛏️",
        "Постоянные улучшения": "⚙️",
        "Припасы и билеты": "🎟️",
        "Особые награды": "🏆",
    }
    prices = mine_resource_prices()
    merchant_items = [
        {
            "key": key,
            "name": str(MINE_RESOURCE_CATALOG[key]["title"]),
            "emoji": str(MINE_RESOURCE_CATALOG[key]["emoji"]),
            "quantity": int(items.get(key, 0)),
            "price": int(prices[key]),
            "total": int(items.get(key, 0)) * int(prices[key]),
            "rarity": str(MINE_RESOURCE_CATALOG[key]["rarity"]),
        }
        for key in MINE_RESOURCE_ORDER
    ]
    merchant_total = sum(item["total"] for item in merchant_items)
    inventory = [
        {"title": title, "icon": icons[title], "items": values}
        for title, values in grouped.items()
        if values
    ]
    return {
        "coins": db.get_dig_player(0, user_id).coins,
        "categories": categories,
        "inventory": inventory,
        "merchant": {
            "items": merchant_items,
            "total": merchant_total,
            "nextPriceChangeText": "Цены меняются каждый час.",
        },
    }


@router.get("/miniapp/shop")
def miniapp_shop(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not db.get_dig_player(0, user["id"]):
            raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
        return _shop_catalog(db, user["id"])
    finally:
        db.close()


@router.post("/miniapp/shop/buy")
def miniapp_shop_buy(
    response: Response,
    payload: ShopPurchase,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    with DIG_LOCK:
        db = _db()
        try:
            player = db.get_dig_player(0, user["id"])
            if not player:
                raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
            item = game.DIG_SHOP_ITEMS.get(payload.item_key)
            if not item or payload.item_key == "prank":
                raise HTTPException(400, "Этот товар нельзя купить в Mini App.")
            items = _items_map(db, user["id"])
            purchase_error = game.dig_purchase_error(items, payload.item_key)
            if purchase_error:
                raise HTTPException(400, purchase_error)
            status = db.purchase_dig_item(
                0,
                user["id"],
                payload.item_key,
                game.dig_shop_price(payload.item_key, items),
                quantity=1,
                unique=payload.item_key in game.DIG_PERMANENT_ITEMS,
            )
            if status == "owned":
                raise HTTPException(400, "Это постоянное улучшение уже куплено.")
            if status == "no_coins":
                raise HTTPException(400, "Не хватает котоинов.")
            response.headers["X-Miniapp-Shop-Item-Key"] = payload.item_key
            response.headers["X-Miniapp-Shop-Item-Quantity"] = str(
                db.get_dig_item_quantity(0, user["id"], payload.item_key)
            )
            return {"ok": True, "item": payload.item_key, "state": _state(db, user["id"]), "shop": _shop_catalog(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/shop/star-invoice")
async def miniapp_shop_star_invoice(
    payload: ShopPurchase,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, str]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    if payload.item_key not in game.DIG_STAR_ACTIONS:
        raise HTTPException(400, "Этот товар нельзя купить за Stars.")

    db = _db()
    try:
        if not db.get_dig_player(0, user["id"]):
            raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
    finally:
        db.close()

    title, description, price = game.dig_star_invoice(payload.item_key)
    bot = Bot(token=load_config().bot_token)
    try:
        link = await bot.create_invoice_link(
            title=title,
            description=description,
            payload=game.dig_star_payload(payload.item_key, user["id"], 0),
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
            provider_token="",
        )
        return {"url": link}
    finally:
        await bot.session.close()


@router.post("/miniapp/shop/use")
def miniapp_shop_use(
    payload: ShopPurchase,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    with DIG_LOCK:
        db = _db()
        try:
            player = db.get_dig_player(0, user["id"])
            if not player:
                raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
            if payload.item_key != "tea":
                raise HTTPException(400, "Этот предмет нельзя использовать вручную.")
            if not db.consume_dig_item(0, user["id"], "tea"):
                raise HTTPException(400, "В сумке нет чая.")
            now = datetime.now(timezone.utc)
            luck = _refreshed_luck(db, game, user["id"], player.luck, player.last_luck_at, now)
            restored_luck = min(100, luck + 35)
            db.set_dig_luck(0, user["id"], restored_luck, now.isoformat(timespec="seconds"))
            return {
                "ok": True,
                "item": payload.item_key,
                "message": f"Чай использован. Удача: {restored_luck}/100.",
                "state": _state(db, user["id"]),
                "shop": _shop_catalog(db, user["id"]),
            }
        finally:
            db.close()


@router.post("/miniapp/merchant/sell")
def miniapp_merchant_sell(
    payload: MerchantSale,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            _ensure_mine_not_blocked(db, user["id"])
            if not db.get_dig_player(0, user["id"]):
                raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
            prices = mine_resource_prices()
            item_keys = [payload.item_key] if payload.item_key else list(MINE_RESOURCE_ORDER)
            sold: list[dict[str, Any]] = []
            total = 0
            for key in item_keys:
                if key not in MINE_RESOURCE_CATALOG:
                    raise HTTPException(400, "Этот ресурс торговец не покупает.")
                quantity = db.get_dig_item_quantity(0, user["id"], key)
                if quantity <= 0:
                    continue
                if not db.consume_dig_items(0, user["id"], key, quantity):
                    continue
                price = int(prices[key])
                amount = quantity * price
                total += amount
                sold.append(
                    {
                        "key": key,
                        "name": str(MINE_RESOURCE_CATALOG[key]["title"]),
                        "quantity": quantity,
                        "price": price,
                        "total": amount,
                    }
                )
            if total <= 0:
                raise HTTPException(400, "Продавать пока нечего.")
            db.add_dig_coins(0, user["id"], total)
            return {
                "ok": True,
                "sold": sold,
                "total": total,
                "message": f"Торговец купил добычу за {total} котоинов.",
                "state": _state(db, user["id"]),
                "shop": _shop_catalog(db, user["id"]),
            }
        finally:
            db.close()


@router.get("/miniapp/shop/gift-targets")
def miniapp_shop_gift_targets(
    item_key: str = Query(min_length=1, max_length=64),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    db = _db()
    try:
        if not db.get_dig_player(0, user["id"]):
            raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
        item = game.DIG_SHOP_ITEMS.get(item_key)
        target_kind = _gift_target_kind(game, item_key)
        if not item or target_kind is None:
            raise HTTPException(400, "Этот предмет нельзя подарить.")
        return {
            "item": {"key": item_key, "name": item[0], "quantity": db.get_dig_item_quantity(0, user["id"], item_key)},
            "targetKind": target_kind,
            "targets": _gift_recipients(db, game, user["id"], item_key),
        }
    finally:
        db.close()


@router.post("/miniapp/shop/gift")
def miniapp_shop_gift(
    payload: ShopGiftSend,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    with DIG_LOCK:
        db = _db()
        try:
            player = db.get_dig_player(0, user["id"])
            if not player:
                raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
            item = game.DIG_SHOP_ITEMS.get(payload.item_key)
            target_kind = _gift_target_kind(game, payload.item_key)
            if not item or target_kind is None:
                raise HTTPException(400, "Этот предмет нельзя подарить.")
            if payload.target_user_id == user["id"]:
                raise HTTPException(400, "Себе подарки не отправляем. Даже если очень хочется.")
            if not db.get_dig_player(0, payload.target_user_id):
                raise HTTPException(400, "Получатель ещё не зарегистрирован в шахте.")

            recipients = _gift_recipients(db, game, user["id"], payload.item_key)
            target = next((item for item in recipients if int(item["id"]) == payload.target_user_id), None)
            if target is None:
                if target_kind == "partner":
                    raise HTTPException(400, "Этот подарок можно отправить только текущей паре.")
                raise HTTPException(400, "Этого пользователя нет в списке друзей для подарка.")

            if not db.consume_dig_item(0, user["id"], payload.item_key):
                raise HTTPException(400, "В сумке больше нет этого подарка.")
            db.add_dig_item(0, payload.target_user_id, payload.item_key, 1)

            return {
                "ok": True,
                "item": payload.item_key,
                "message": f"Подарок «{item[0]}» отправлен пользователю {target['fullName']}.",
                "target": target,
                "state": _state(db, user["id"]),
                "shop": _shop_catalog(db, user["id"]),
            }
        finally:
            db.close()


def _settle_interactive_manual(
    db: Database,
    game: Any,
    user: dict[str, Any],
    session: dict[str, Any],
    now: datetime,
    *,
    collapsed: bool,
) -> str:
    uid = user["id"]
    player_before = db.get_dig_player(0, uid)
    if not player_before:
        db.finish_interactive_dig_session(session["id"], "cancelled")
        return "Игрок не найден, вылазка закрыта."
    snapshot = json.loads(session["equipment_snapshot"] or "{}")
    depth = int(session["depth"])
    temporary = int(session["temporary_coins"])
    if collapsed:
        coins, lost = collapse_payout(temporary, int(snapshot.get("loss_protection", 0)))
    else:
        coins, lost = temporary, 0
    effects = list(snapshot.get("used_effects") or [])
    items = _items_map(db, uid)
    event = None
    artifact = None
    if depth > 0 and not collapsed:
        before_event = coins
        coins, event = game.dig_random_event(depth, coins)
        if coins < before_event and items.get("medkit", 0) > 0 and db.consume_dig_item(0, uid, "medkit"):
            coins = before_event
            _remember_repair_candidate(snapshot, "medkit")
            effects.append("Аптечка: потеря котоинов отменена")
        artifact_bonus = max(0, int((float(snapshot.get("route_artifacts", 1.0)) - 1) * 10))
        artifact_coins, artifact = _find_artifact(
            db,
            game,
            uid,
            depth,
            items,
            artifact_bonus + (15 if snapshot.get("map_used") else 0),
        )
        coins += artifact_coins
        if snapshot.get("talisman_used"):
            coins *= 2
            effects.append("Талисман: котоины удвоены")
    if depth >= INTERACTIVE_DIG_MAX_DEPTH and not collapsed:
        final_bonus, final_text = final_depth_bonus(depth, str(snapshot.get("mine_key") or "old_mine"))
        coins += final_bonus
        effects.append(final_text)

    if depth > 0:
        _grant_snapshot_resources(db, uid, snapshot, effects)

    _apply_interactive_repair_kit(db, game, 0, uid, snapshot, effects)

    text = now.isoformat(timespec="seconds")
    db.update_dig_player_after_dig(
        0,
        uid,
        user.get("username"),
        user["full_name"],
        coins,
        depth,
        depth,
        int(snapshot.get("luck_after", player_before.luck)),
        text,
        text,
    )
    db.add_dig_weekly_depth(uid, game.dig_week_start(now), depth)
    contract_updates = _update_contracts(db, game, uid, depth, coins, artifact is not None)
    progress = db.update_dig_progress(uid, 5 + depth * 10, depth > 0, session["route_key"])
    expedition = db.add_dig_expedition_progress(0, uid, now.date().isoformat(), depth, game.DIG_EXPEDITION_TARGET)
    if expedition["completed"]:
        db.reward_dig_expedition(0, now.date().isoformat(), game.DIG_EXPEDITION_REWARD)
    if depth > 0 and game.find_golden_ticket(depth):
        db.add_dig_item(0, uid, "golden_ticket", 1)
        effects.append("Золотой билет найден")
    db.finish_interactive_dig_session(session["id"], "collapsed" if collapsed else "finished")
    lines = [
        "Обвал!" if collapsed else ("Финальная комната завершена!" if depth >= INTERACTIVE_DIG_MAX_DEPTH else "Добыча забрана."),
        f"Глубина: {depth} м",
        f"+{coins} котоинов",
        f"Уровень {progress['level']}, XP {progress['xp']}",
    ]
    if lost:
        lines.append(f"Обвал унёс {lost} котоинов.")
    if event:
        lines.append(event)
    if artifact:
        lines.append(artifact)
    if contract_updates:
        lines.append("Контракты: " + "; ".join(contract_updates))
    if effects:
        lines.append("Эффекты: " + "; ".join(str(item) for item in effects[-6:]))
    return "\n".join(lines)


@router.post("/miniapp/mine/shift")
def miniapp_shift_contract(
    payload: ShiftContractPick,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    from . import bot as game

    with DIG_LOCK:
        db = _db()
        try:
            if not db.get_dig_player(0, user["id"]):
                raise HTTPException(400, "Сначала зарегистрируйтесь в шахте.")
            error = _select_rank_shift_contract(db, game, user["id"], payload.contract_key)
            if error:
                raise HTTPException(400, error)
            return {"ok": True, "state": _state(db, user["id"])}
        finally:
            db.close()


@router.get("/miniapp/mine")
def miniapp_mine(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        return _state(db, user["id"])
    finally:
        db.close()


@router.get("/miniapp/profile")
async def miniapp_profile(
    user_id: int | None = Query(default=None, ge=1),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    viewer_id = int(user["id"])
    target_id = int(user_id or viewer_id)
    config = load_config()
    db = Database(config.db_path)
    premium = PremiumService(config.db_path)
    try:
        db.init()
        relation = _miniapp_social_target(db, viewer_id, target_id)
        if relation is None and not _miniapp_can_manage_roles(viewer_id):
            raise HTTPException(403, "Этот профиль доступен только вам, друзьям или паре.")
        if relation is None:
            relation = {"relation": "owner", "relationTitle": "Владелец"}
        target = db.get_dig_player(0, target_id)
        known_target = db.get_known_user(target_id)
        if not target and target_id != viewer_id and not known_target:
            raise HTTPException(404, "Профиль не найден.")
        photo_url = str(user.get("photo_url") or "") if target_id == viewer_id else _miniapp_avatar_url(target_id)
        if target_id == viewer_id and not photo_url:
            photo_url = _miniapp_avatar_url(target_id)
        profile = build_user_profile(
            db,
            premium,
            target_id,
            target.username if target else (known_target.username if known_target else user.get("username")),
            target.full_name if target else (known_target.full_name if known_target else user["full_name"]),
            photo_url=photo_url,
        )
        profile["roles"] = _miniapp_profile_roles(db, target_id)
        target_people = _miniapp_social_people(db, target_id)
        if target_id == viewer_id:
            people = target_people
        else:
            accessible_ids = {viewer_id, *(int(item["id"]) for item in _miniapp_social_people(db, viewer_id))}
            people = [item for item in target_people if int(item["id"]) in accessible_ids]
        partner = next((item for item in people if item["relation"] == "partner"), None)
        profile["viewer"] = {
            "id": viewer_id,
            "isSelf": target_id == viewer_id,
            "isOwner": _miniapp_can_manage_roles(viewer_id),
            "isAppAdmin": _miniapp_is_app_admin(db, viewer_id),
            "canManageRoles": _miniapp_can_manage_roles(viewer_id),
            "canViewAdminPanel": _miniapp_can_view_admin_panel(db, viewer_id),
            "canViewMineAdmin": _miniapp_can_view_mine_admin(db, viewer_id),
            "canManageMineAdmin": _miniapp_can_manage_mine_admin(db, viewer_id),
        }
        profile["social"] = {
            "relation": relation.get("relation", "friend"),
            "relationTitle": relation.get("relationTitle", "Друг"),
            "friendsCount": len([item for item in people if item["relation"] == "friend"]),
            "friends": people[:40],
            "partner": partner,
        }
        return profile
    finally:
        premium.close()
        db.close()


@router.get("/miniapp/profile/roles")
def miniapp_profile_roles(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    if not _miniapp_can_manage_roles(user["id"]):
        raise HTTPException(403, "Управление ролями доступно только владельцу.")
    db = _db()
    try:
        return {
            "items": db.list_miniapp_profile_roles_by_label(list(MINIAPP_ASSIGNABLE_ROLE_LABELS)),
            "groups": _miniapp_profile_role_groups(db),
        }
    finally:
        db.close()


@router.post("/miniapp/profile/roles")
def miniapp_profile_role_set(
    payload: ProfileRoleSet,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    if not _miniapp_can_manage_roles(user["id"]):
        raise HTTPException(403, "Управление ролями доступно только владельцу.")
    label = _normalize_profile_role_label(payload.label)
    db = _db()
    try:
        target_id, full_name, username = _resolve_profile_role_target(db, payload.target)
        db.set_miniapp_profile_role(target_id, label, user["id"])
        role = db.get_miniapp_profile_role(target_id)
        return {
            "ok": True,
            "target": {"id": target_id, "fullName": full_name, "username": username or ""},
            "role": dict(role.__dict__) if role else None,
            "roles": db.list_miniapp_profile_roles_by_label(list(MINIAPP_ASSIGNABLE_ROLE_LABELS)),
            "groups": _miniapp_profile_role_groups(db),
        }
    finally:
        db.close()


@router.post("/miniapp/profile/roles/clear")
def miniapp_profile_role_clear(
    payload: ProfileRoleClear,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    if not _miniapp_can_manage_roles(user["id"]):
        raise HTTPException(403, "Управление ролями доступно только владельцу.")
    db = _db()
    try:
        target_id, full_name, username = _resolve_profile_role_target(db, payload.target)
        if _miniapp_can_manage_roles(target_id):
            raise HTTPException(400, "Роль владельца нельзя удалить из Mini App.")
        removed_custom = db.clear_miniapp_profile_role(target_id)
        removed_moderator_count = db.clear_all_chat_moderator_roles(target_id)
        return {
            "ok": True,
            "removed": bool(removed_custom or removed_moderator_count),
            "removedModeratorRoles": removed_moderator_count,
            "target": {"id": target_id, "fullName": full_name, "username": username or ""},
            "roles": db.list_miniapp_profile_roles_by_label(list(MINIAPP_ASSIGNABLE_ROLE_LABELS)),
            "groups": _miniapp_profile_role_groups(db),
        }
    finally:
        db.close()


@router.get("/miniapp/profile/admin")
def miniapp_profile_admin_panel(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not _miniapp_can_view_admin_panel(db, user["id"]):
            raise HTTPException(403, "Админ-панель Mini App доступна владельцу и админам.")
        is_owner = _miniapp_can_manage_roles(user["id"])
        admins = db.list_miniapp_profile_roles_by_label(["Админ"])
        moderators = db.list_all_chat_moderators()
        chats = db.list_chats()
        return {
            "ok": True,
            "viewerRole": "owner" if is_owner else "admin",
            "canManageRoles": is_owner,
            "canManageMine": _miniapp_can_manage_mine_admin(db, user["id"]),
            "summary": {
                "chats": len(chats),
                "admins": len(admins) + (1 if _miniapp_owner_id() is not None else 0),
                "moderators": len({int(row["user_id"]) for row in moderators}),
                "minePlayers": db.count_dig_players(),
                "triggers": sum(len(db.list_triggers(chat.chat_id)) for chat in chats),
            },
            "sections": [
                {"key": "roles", "title": "Роли", "enabled": is_owner, "description": "Выдача ролей приложения."},
                {"key": "mine", "title": "Шахта", "enabled": _miniapp_can_manage_mine_admin(db, user["id"]), "description": "Управление игроками шахты."},
                {"key": "moderation", "title": "Модерация", "enabled": False, "description": "Права и действия перенесём следующим шагом."},
                {"key": "triggers", "title": "Триггеры", "enabled": _miniapp_can_manage_triggers(db, user["id"]), "description": "Слова и фразы, на которые бот отвечает в чатах."},
            ],
        }
    finally:
        db.close()


@router.get("/miniapp/profile/triggers")
def miniapp_profile_triggers(
    chat_id: int | None = Query(default=None),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not _miniapp_can_manage_triggers(db, user["id"]):
            raise HTTPException(403, "Триггеры доступны владельцу и админам Mini App.")
        chats = db.list_chats()
        selected_chat_id = int(chat_id) if chat_id is not None else (int(chats[0].chat_id) if chats else 0)
        selected_chat = db.get_chat(selected_chat_id) if selected_chat_id else None
        triggers = db.list_triggers(selected_chat_id) if selected_chat else []
        return {
            "ok": True,
            "canManage": True,
            "selectedChatId": selected_chat_id if selected_chat else 0,
            "selectedChat": _miniapp_chat_public(selected_chat) if selected_chat else None,
            "chats": [_miniapp_chat_public(chat) for chat in chats],
            "triggers": [_miniapp_trigger_public(db, item) for item in triggers],
        }
    finally:
        db.close()


@router.post("/miniapp/profile/triggers")
def miniapp_profile_trigger_save(
    payload: MiniAppTriggerSave,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not _miniapp_can_manage_triggers(db, user["id"]):
            raise HTTPException(403, "Триггеры доступны владельцу и админам Mini App.")
        if db.get_chat(payload.chatId) is None:
            raise HTTPException(404, "Чат не найден.")
        normalized = normalize_trigger(payload.trigger)
        if not normalized:
            raise HTTPException(400, "Укажи слово или фразу для триггера.")
        existing = next((item for item in db.list_triggers(payload.chatId) if item.trigger == normalized), None)
        if not payload.variants and payload.text is not None and existing and existing.media_type and existing.media_file_id:
            payload.variants.append(
                MiniAppTriggerVariant(
                    variantType=existing.media_type,
                    text=payload.text,
                    mediaType=existing.media_type,
                    mediaFileId=existing.media_file_id,
                )
            )
        variants = _clean_trigger_variants(payload)
        db.replace_trigger_variants(payload.chatId, normalized, variants, user["id"])
        saved = next((item for item in db.list_triggers(payload.chatId) if item.trigger == normalized), None)
        return {
            "ok": True,
            "message": "Триггер сохранён.",
            "trigger": _miniapp_trigger_public(db, saved) if saved else None,
        }
    finally:
        db.close()


@router.post("/miniapp/profile/triggers/media")
async def miniapp_profile_trigger_media_upload(
    media_type: str,
    file: UploadFile = File(...),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not _miniapp_can_manage_triggers(db, user["id"]):
            raise HTTPException(403, "Триггеры доступны владельцу и админам Mini App.")
    finally:
        db.close()
    normalized_type = media_type.strip().casefold()
    if normalized_type == "gif":
        normalized_type = "animation"
    if normalized_type not in TRIGGER_MEDIA_TYPES:
        raise HTTPException(400, "Неподдерживаемый тип медиа.")
    content_type = (file.content_type or "").split(";", 1)[0].strip().casefold()
    allowed = TRIGGER_MEDIA_TYPES[normalized_type]
    if content_type and content_type not in allowed:
        raise HTTPException(400, "Файл не похож на выбранный тип медиа.")
    suffix = Path(file.filename or "").suffix.lower()
    if not suffix:
        suffix = ".gif" if normalized_type == "animation" else ".mp3" if normalized_type == "audio" else ".jpg"
    target = _trigger_media_dir() / f"{int(time.time())}_{secrets.token_hex(10)}{suffix}"
    size = 0
    with target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > TRIGGER_MEDIA_MAX_BYTES:
                with suppress(OSError):
                    target.unlink()
                raise HTTPException(400, "Файл слишком большой для триггера.")
            fh.write(chunk)
    if normalized_type == "audio":
        try:
            import av  # type: ignore

            with av.open(str(target)) as container:
                duration = float(container.duration or 0) / 1_000_000 if container.duration else 0.0
            if duration and duration > 30.5:
                with suppress(OSError):
                    target.unlink()
                raise HTTPException(400, "Аудио-метка должна быть до 30 секунд.")
        except HTTPException:
            raise
        except Exception:
            with suppress(OSError):
                target.unlink()
            raise HTTPException(400, "Не удалось проверить длительность аудио.")
    return {
        "ok": True,
        "mediaType": normalized_type,
        "mediaFileId": f"local:{target}",
        "fileName": file.filename or target.name,
        "size": size,
    }


@router.post("/miniapp/profile/triggers/delete")
def miniapp_profile_trigger_delete(
    payload: MiniAppTriggerDelete,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        if not _miniapp_can_manage_triggers(db, user["id"]):
            raise HTTPException(403, "Триггеры доступны владельцу и админам Mini App.")
        if db.get_chat(payload.chatId) is None:
            raise HTTPException(404, "Чат не найден.")
        normalized = normalize_trigger(payload.trigger)
        deleted = db.delete_trigger(payload.chatId, normalized)
        return {
            "ok": True,
            "deleted": deleted,
            "message": "Триггер удалён." if deleted else "Такой триггер уже не найден.",
        }
    finally:
        db.close()


@router.get("/miniapp/profile/mine-admin")
def miniapp_profile_mine_admin(
    page: int = 1,
    per_page: int = 20,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    safe_page = max(1, int(page))
    safe_per_page = max(1, min(50, int(per_page)))
    offset = (safe_page - 1) * safe_per_page
    db = _db()
    try:
        if not _miniapp_can_view_mine_admin(db, user["id"]):
            raise HTTPException(403, "Панель шахты доступна владельцу и модераторам.")
        total = db.count_dig_players()
        players = db.list_dig_players_page(limit=safe_per_page, offset=offset)
        can_manage = _miniapp_can_manage_mine_admin(db, user["id"])
        return {
            "canManage": can_manage,
            "viewerRole": "admin" if can_manage else "moderator",
            "summary": {
                "players": total,
                "totalDepth": sum(int(player.total_depth) for player in db.list_all_dig_players()),
                "activeSessions": 0,
            },
            "top": {
                "depth": [_miniapp_dig_player_public(db, player) for player in db.top_dig_depth(0, limit=10)],
                "coins": [_miniapp_dig_player_public(db, player) for player in db.top_dig_coins(0, limit=10)],
            },
            "players": {
                "items": [_miniapp_dig_player_public(db, player) for player in players],
                "total": total,
                "page": safe_page,
                "perPage": safe_per_page,
            },
            "blocked": [_miniapp_dig_block_public(item) for item in db.list_dig_blocks()],
        }
    finally:
        db.close()


@router.post("/miniapp/profile/mine-admin/grant")
def miniapp_profile_mine_admin_grant(
    payload: MineAdminGrant,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            if not _miniapp_can_manage_mine_admin(db, user["id"]):
                raise HTTPException(403, "Управление шахтой доступно владельцу и админам Mini App.")
            if db.get_dig_player(0, payload.userId) is None:
                raise HTTPException(404, "Игрок шахты с таким User ID не зарегистрирован.")
            if payload.coins is not None:
                db.add_dig_coins(0, payload.userId, payload.coins)
            if payload.luck is not None:
                db.set_dig_luck(0, payload.userId, payload.luck, datetime.now(timezone.utc).isoformat(timespec="seconds"))
            if payload.extraDigs is not None:
                db.adjust_dig_item(0, payload.userId, "star_dig", payload.extraDigs)
            if payload.goldenTickets is not None:
                db.adjust_dig_item(0, payload.userId, "golden_ticket", payload.goldenTickets)
            if payload.superPasses is not None:
                db.adjust_dig_item(0, payload.userId, "super_game_pass", payload.superPasses)
            if payload.clearCooldown:
                db.clear_dig_cooldown(0, payload.userId)
            player = db.get_dig_player(0, payload.userId)
            return {
                "ok": True,
                "player": _miniapp_dig_player_public(db, player) if player else None,
                "message": "Шахта игрока обновлена.",
            }
        finally:
            db.close()


@router.post("/miniapp/profile/mine-admin/delete")
def miniapp_profile_mine_admin_delete(
    payload: MineAdminTarget,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            if not _miniapp_can_manage_mine_admin(db, user["id"]):
                raise HTTPException(403, "Управление шахтой доступно владельцу и админам Mini App.")
            deleted = db.delete_dig_player(payload.userId)
            return {"ok": True, "deleted": deleted, "message": "Игрок удалён из шахты." if deleted else "Игрока в шахте уже не было."}
        finally:
            db.close()


@router.post("/miniapp/profile/mine-admin/block")
def miniapp_profile_mine_admin_block(
    payload: MineAdminTarget,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            if not _miniapp_can_manage_mine_admin(db, user["id"]):
                raise HTTPException(403, "Управление шахтой доступно владельцу и админам Mini App.")
            db.block_dig_user(payload.userId, user["id"], payload.reason)
            deleted = db.delete_dig_player(payload.userId) if payload.deletePlayer else False
            return {
                "ok": True,
                "deleted": deleted,
                "message": "Игрок заблокирован в шахте." + (" Прогресс удалён." if deleted else ""),
            }
        finally:
            db.close()


@router.post("/miniapp/profile/mine-admin/unblock")
def miniapp_profile_mine_admin_unblock(
    payload: MineAdminTarget,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            if not _miniapp_can_manage_mine_admin(db, user["id"]):
                raise HTTPException(403, "Управление шахтой доступно владельцу и админам Mini App.")
            removed = db.unblock_dig_user(payload.userId)
            return {"ok": True, "removed": removed, "message": "Блокировка снята." if removed else "Блокировки уже не было."}
        finally:
            db.close()


@router.get("/miniapp/avatar/{user_id}")
async def miniapp_avatar(user_id: int, sig: str = "") -> FileResponse:
    if not _valid_miniapp_avatar_signature(user_id, sig):
        raise HTTPException(403, "Avatar link is invalid")
    path = await _ensure_miniapp_avatar(user_id)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Avatar not found")
    return FileResponse(path, media_type="image/jpeg", filename=f"user_{user_id}.jpg")


@router.get("/miniapp/weather")
async def miniapp_weather(
    q: str,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _telegram_user(x_telegram_init_data)
    from .admin_api import weather_payload

    return await weather_payload(q, "MonkeyDin-MiniApp/0.3")


@router.get("/miniapp/radio/search")
async def miniapp_radio_search(
    q: str = "",
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    _telegram_user(x_telegram_init_data)
    query = q.strip()
    params = {
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
        "limit": "30",
    }
    if query:
        params["name"] = query
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://de1.api.radio-browser.info/json/stations/search",
                params=params,
                headers={"User-Agent": "MonkeyDin-MiniApp/0.3"},
            ) as response:
                if response.status != 200:
                    raise HTTPException(502, "Radio Browser временно недоступен.")
                stations = await response.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise HTTPException(502, "Не удалось связаться с Radio Browser.") from exc
    return {"items": [_radio_station_public(station) for station in (stations or []) if station.get("url_resolved") or station.get("url")]}


@router.post("/miniapp/radio/click")
async def miniapp_radio_click(
    payload: ShopPurchase,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, bool]:
    _telegram_user(x_telegram_init_data)
    station_uuid = payload.item_key.strip()
    if not station_uuid:
        return {"ok": False}
    timeout = aiohttp.ClientTimeout(total=4)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://de1.api.radio-browser.info/json/url/{station_uuid}",
                headers={"User-Agent": "MonkeyDin-MiniApp/0.3"},
            ):
                pass
    except aiohttp.ClientError:
        pass
    return {"ok": True}


@router.get("/miniapp/radio/stream")
async def miniapp_radio_stream(token: str) -> StreamingResponse:
    from .admin_api import PinnedPublicResolver, resolve_public_stream_url

    raw_url = _radio_stream_url(token)
    checked_url, hostname, addresses = resolve_public_stream_url(raw_url)
    connector = aiohttp.TCPConnector(
        resolver=PinnedPublicResolver(hostname, addresses),
        use_dns_cache=False,
        force_close=True,
        limit=1,
    )
    timeout = aiohttp.ClientTimeout(total=None, connect=12, sock_read=30)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout, auto_decompress=False)

    async def stream() -> Any:
        response = None
        try:
            response = await session.get(
                checked_url,
                allow_redirects=False,
                headers={"User-Agent": "MonkeyDin-MiniApp/0.3", "Icy-MetaData": "0"},
            )
            if response.status < 200 or response.status >= 300:
                return
            async for chunk in response.content.iter_chunked(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            if response is not None:
                response.close()
            await session.close()

    return StreamingResponse(
        stream(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/miniapp/mine/register")
def miniapp_register(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
        _ensure_mine_not_blocked(db, user["id"])
        db.register_dig_player(0, user["id"], user.get("username"), user["full_name"])
        return _state(db, user["id"])
    finally:
        db.close()


@router.post("/miniapp/gold-ticket/start")
def gold_ticket_start(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            active = _ticket_public(db, user["id"])
            if active:
                return {"ok": True, "game": active, "state": _state(db, user["id"])}
            if not db.consume_dig_item(0, user["id"], "golden_ticket"):
                raise HTTPException(400, "У тебя нет золотого билета.")
            cells = [0] * 9
            for cell, prize in zip(secrets.SystemRandom().sample(range(9), 3), (10, 25, 50)):
                cells[cell] = prize
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.save_gold_ticket_game(user["id"], json.dumps(cells), "[]", 3, now)
            return {"ok": True, "game": _ticket_public(db, user["id"]), "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/gold-ticket/pick")
def gold_ticket_pick(
    payload: TicketPick,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            game = db.get_gold_ticket_game(user["id"])
            if not game:
                raise HTTPException(400, "Сначала открой золотой билет.")
            opened = json.loads(game["opened_json"] or "[]")
            if payload.cell in opened:
                raise HTTPException(400, "Эта клетка уже открыта.")
            if int(game["attempts_left"]) <= 0:
                raise HTTPException(400, "Попытки закончились.")
            cells = json.loads(game["cells_json"])
            prize = int(cells[payload.cell])
            opened.append(payload.cell)
            attempts_left = int(game["attempts_left"]) - 1
            if prize:
                db.add_dig_coins(0, user["id"], prize)
            if attempts_left <= 0:
                db.clear_gold_ticket_game(user["id"])
                next_game = None
            else:
                db.save_gold_ticket_game(user["id"], game["cells_json"], json.dumps(opened), attempts_left, game["created_at"])
                next_game = _ticket_public(db, user["id"])
            return {"ok": True, "cell": payload.cell, "prize": prize, "attemptsLeft": attempts_left, "game": next_game, "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/super-game/start")
def super_game_start(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            active = _super_ticket_public(db, user["id"])
            if active:
                return {"ok": True, "game": active, "state": _state(db, user["id"])}
            if db.get_dig_item_quantity(0, user["id"], "golden_ticket") >= 3:
                db.consume_dig_items(0, user["id"], "golden_ticket", 3)
                source = "tickets"
            elif db.consume_dig_item(0, user["id"], "super_game_pass"):
                source = "stars"
            else:
                raise HTTPException(400, "Нужно 3 золотых билета или доступ к супер-игре за 10 ⭐.")

            cells: list[int | str] = [0] * 81
            positions = secrets.SystemRandom().sample(range(81), 18)
            for cell, prize in zip(positions[:10], (50, 75, 100, 125, 150, 175, 200, 225, 250, 250)):
                cells[cell] = prize
            for cell in positions[10:15]:
                cells[cell] = 5
            for cell, reward in zip(positions[15:18], ("super:mute30", "super:tag", "super:coins500")):
                cells[cell] = reward
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.save_super_ticket_game(user["id"], json.dumps(cells), "[]", 10, now)
            return {"ok": True, "source": source, "game": _super_ticket_public(db, user["id"]), "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/super-game/invoice")
async def super_game_invoice(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, str]:
    user = _telegram_user(x_telegram_init_data)
    bot = Bot(token=load_config().bot_token)
    try:
        link = await bot.create_invoice_link(
            title="Супер-игра 9×9",
            description="10 попыток, 10 денежных призов, 5 призов по 5 котоинов и три сундука с особыми наградами.",
            payload=f"dig_star:super_game:{user['id']}:0:{secrets.token_hex(12)}",
            currency="XTR",
            prices=[LabeledPrice(label="Супер-игра 9×9", amount=10)],
            provider_token="",
        )
        return {"url": link}
    finally:
        await bot.session.close()


@router.post("/miniapp/super-game/pick")
def super_game_pick(
    response: Response,
    payload: SuperTicketPick,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            game = db.get_super_ticket_game(user["id"])
            if not game:
                raise HTTPException(400, "Сначала открой супер-игру.")
            opened = json.loads(game["opened_json"] or "[]")
            if payload.cell in opened:
                raise HTTPException(400, "Эта клетка уже открыта.")
            if int(game["attempts_left"]) <= 0:
                raise HTTPException(400, "Попытки закончились.")
            cells = json.loads(game["cells_json"])
            reward = cells[payload.cell]
            opened.append(payload.cell)
            attempts_left = int(game["attempts_left"]) - 1
            reward_key = None
            if isinstance(reward, int) and reward > 0:
                db.add_dig_coins(0, user["id"], reward)
            elif reward == "super:mute30":
                db.add_dig_item(0, user["id"], "super_mute30", 1)
                reward_key = "mute30"
            elif reward == "super:tag":
                db.add_dig_item(0, user["id"], "super_tag", 1)
                reward_key = "tag"
            elif reward == "super:coins500":
                db.add_dig_coins(0, user["id"], 500)
                reward_key = "coins500"
            if attempts_left <= 0:
                db.clear_super_ticket_game(user["id"])
                next_game = None
                response.headers["X-Miniapp-Super-Game-Finished"] = "1"
            else:
                db.save_super_ticket_game(user["id"], game["cells_json"], json.dumps(opened), attempts_left, game["created_at"])
                next_game = _super_ticket_public(db, user["id"])
            return {"ok": True, "cell": payload.cell, "coins": reward if isinstance(reward, int) else 0,
                    "reward": reward_key, "attemptsLeft": attempts_left, "game": next_game,
                    "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/interactive/start")
def miniapp_interactive_start(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            _ensure_mine_not_blocked(db, user["id"])
            _begin_interactive_manual(db, game, user, datetime.now(timezone.utc))
            return {"ok": True, "message": "Вылазка началась.", "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/interactive/cell")
def miniapp_interactive_cell(
    payload: MineCellPick,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            _ensure_mine_not_blocked(db, user["id"])
            session = db.get_active_interactive_dig_session(user["id"])
            if not session:
                raise HTTPException(400, "Сначала начни вылазку.")
            stage = json.loads(session["cells_json"] or "{}")
            if isinstance(stage, dict) and stage.get("type") != "cells":
                raise HTTPException(400, "Сейчас нужно выбрать действие события.")
            cells = _interactive_cells(stage)
            used = [int(item) for item in json.loads(session["used_cells_json"] or "[]")]
            if payload.cell in used:
                raise HTTPException(400, "Эта клетка уже проверена.")
            if payload.cell >= len(cells):
                raise HTTPException(400, "Клетка не найдена.")
            snapshot = json.loads(session["equipment_snapshot"] or "{}")
            current_depth = int(session["depth"])
            next_depth = current_depth + 1
            resolved = resolve_cell(cells[payload.cell])
            if int(cells[payload.cell].get("bonus", 0)):
                resolved["chance_modifier"] = float(resolved.get("chance_modifier", 0.0)) + int(cells[payload.cell].get("bonus", 0))
            chance = final_cell_chance(float(game.DIG_SUCCESS_CHANCES[next_depth - 1]), float(snapshot.get("chance_bonus", 0.0)), resolved)
            success = secrets.randbelow(10000) < int(chance * 100)
            cell_name = {"normal": "обычный грунт", "ore": "рудная жила", "hard": "твёрдая порода", "roots": "странные корни"}.get(str(resolved.get("resolved_kind")), "слой")
            if success:
                gained = cell_reward(game.dig_coin_reward(next_depth), float(snapshot.get("route_coins", 1.0)), resolved, int(snapshot.get("coin_bonus_percent", 0)))
                if int(cells[payload.cell].get("reward_bonus", 0)):
                    gained = (gained * (100 + int(cells[payload.cell].get("reward_bonus", 0))) + 99) // 100
                gained = scale_interactive_reward(gained)
                resource_drops = mined_resource_drops(resolved, str(snapshot.get("mine_key") or "old_mine"), next_depth)
                if resource_drops:
                    _add_snapshot_resources(snapshot, resource_drops)
                ore_text = f" Добыча: {resource_stack_text(resource_drops)}." if resource_drops else ""
                if next_depth >= INTERACTIVE_DIG_MAX_DEPTH:
                    next_stage = generate_dig_stage(INTERACTIVE_DIG_MAX_DEPTH, str(snapshot.get("mine_key") or "old_mine"))
                    db.update_interactive_dig_session(
                        session["id"],
                        depth=INTERACTIVE_DIG_MAX_DEPTH - 1,
                        temporary_coins=int(session["temporary_coins"]) + gained,
                        cells_json=json.dumps(next_stage, ensure_ascii=False),
                        used_cells_json="[]",
                        equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                    )
                    return {"ok": True, "message": f"Слой пройден: {cell_name}. +{gained} котоинов.{ore_text} Впереди финальная комната.", "state": _state(db, user["id"])}
                next_stage = generate_dig_stage(next_depth + 1, str(snapshot.get("mine_key") or "old_mine"))
                db.update_interactive_dig_session(
                    session["id"],
                    depth=next_depth,
                    temporary_coins=int(session["temporary_coins"]) + gained,
                    cells_json=json.dumps(next_stage, ensure_ascii=False),
                    used_cells_json="[]",
                    equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                )
                return {"ok": True, "message": f"Слой пройден: {cell_name}. +{gained} котоинов.{ore_text}", "state": _state(db, user["id"])}

            used = sorted(set(used) | {payload.cell})
            durability = int(session["durability"])
            saved = False
            if int(snapshot.get("insurance_count", 0)) > 0 and not snapshot.get("insurance_used"):
                if db.consume_dig_item(0, user["id"], "insurance"):
                    snapshot["insurance_used"] = True
                    snapshot["insurance_count"] = max(0, int(snapshot.get("insurance_count", 0)) - 1)
                    _remember_repair_candidate(snapshot, "insurance")
                    saved = True
            protection = min(45, int(snapshot.get("loss_protection", 0)))
            if not saved and protection and secrets.randbelow(100) < protection:
                saved = True
            if not saved:
                effects = list(snapshot.get("used_effects") or [])
                if _use_interactive_medkit(
                    db,
                    game,
                    0,
                    user["id"],
                    snapshot,
                    effects,
                    "Аптечка: потеря прочности отменена",
                ):
                    snapshot["used_effects"] = effects
                    saved = True
                else:
                    durability -= 1
            if durability <= 0:
                db.update_interactive_dig_session(
                    session["id"],
                    durability=0,
                    used_cells_json=json.dumps(used),
                    equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                )
                finished = db.get_interactive_dig_session(session["id"])
                message = _settle_interactive_manual(db, game, user, finished, datetime.now(timezone.utc), collapsed=True)
                return {"ok": True, "finished": True, "message": message, "state": _state(db, user["id"])}
            replacement_stage = None
            if cell_row_is_exhausted(cells, used):
                replacement_stage = replacement_cell_stage(next_depth, str(snapshot.get("mine_key") or "old_mine"))
            db.update_interactive_dig_session(
                session["id"],
                durability=durability,
                cells_json=json.dumps(replacement_stage, ensure_ascii=False) if replacement_stage else None,
                used_cells_json="[]" if replacement_stage else json.dumps(used),
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            )
            suffix = "Страховка/снаряжение спасли прочность." if saved else f"Прочность: {durability}/{INTERACTIVE_DIG_DURABILITY}."
            if replacement_stage:
                suffix += " Этот ряд исчерпан, кот нашёл соседний ход."
            return {"ok": True, "message": f"Слой не поддался: {cell_name}. {suffix}", "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/interactive/tool")
def miniapp_interactive_tool(
    payload: MineToolUse,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            _ensure_mine_not_blocked(db, user["id"])
            session = db.get_active_interactive_dig_session(user["id"])
            if not session:
                raise HTTPException(400, "Сначала начни вылазку.")
            stage = json.loads(session["cells_json"] or "{}")
            if isinstance(stage, dict) and stage.get("type") != "cells":
                raise HTTPException(400, "В этой комнате предмет не нужен.")
            cells = _interactive_cells(stage)
            if not isinstance(stage, dict):
                stage = {"type": "cells", "cells": cells}
            snapshot = json.loads(session["equipment_snapshot"] or "{}")
            tool = payload.item_key
            if tool not in {"flashlight", "map", "dynamite", "miner_hearing", "magnet", "cat_companion"}:
                raise HTTPException(400, "Такого предмета нет.")
            used_tools = set(snapshot.get("used_tools") or [])
            if tool in used_tools or int(snapshot.get(f"{tool}_count", 0)) <= 0:
                raise HTTPException(400, "Этот предмет уже использован.")
            if not db.consume_dig_item(0, user["id"], tool):
                raise HTTPException(400, "Предмета уже нет в сумке.")
            available = list(range(len(cells)))
            message = "Предмет использован."
            if tool == "flashlight" and available:
                index = available[secrets.randbelow(len(available))]
                cells[index]["revealed"] = cells[index].get("kind", "unknown")
                message = f"Фонарь подсветил клетку {index + 1}."
            elif tool == "map":
                preview = generate_dig_cells(int(session["depth"]) + 2, mine_key=str(snapshot.get("mine_key") or "old_mine"))
                emoji = {"normal": "🟫", "ore": "✨", "hard": "🪨", "roots": "🌿", "unknown": "❓"}
                stage["preview"] = " ".join(emoji.get(str(cell.get("kind")), "❓") for cell in preview)
                snapshot["map_used"] = True
                message = "Карта показала следующий ряд."
            elif tool == "dynamite":
                targets = [i for i, cell in enumerate(cells) if cell.get("kind") in {"hard", "unknown", "roots"}] or available
                secrets.SystemRandom().shuffle(targets)
                for index in targets[:3]:
                    cells[index]["revealed"] = cells[index].get("kind", "unknown")
                    cells[index]["bonus"] = int(cells[index].get("bonus", 0)) + 8
                message = "Динамит ослабил несколько клеток."
            used_tools.add(tool)
            snapshot["used_tools"] = sorted(used_tools)
            _remember_repair_candidate(snapshot, tool)
            snapshot[f"{tool}_count"] = max(0, int(snapshot.get(f"{tool}_count", 0)) - 1)
            db.update_interactive_dig_session(
                session["id"],
                cells_json=json.dumps(stage, ensure_ascii=False),
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            )
            return {"ok": True, "message": message, "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/interactive/event")
def miniapp_interactive_event(
    payload: MineEventChoice,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            _ensure_mine_not_blocked(db, user["id"])
            session = db.get_active_interactive_dig_session(user["id"])
            if not session:
                raise HTTPException(400, "Сначала начни вылазку.")
            stage = json.loads(session["cells_json"] or "{}")
            if not isinstance(stage, dict) or stage.get("type") not in {"event", "final"}:
                raise HTTPException(400, "Сейчас нет события.")
            choice = event_choice(stage, payload.choice_key)
            if not choice:
                raise HTTPException(400, "Такого выбора нет.")
            snapshot = json.loads(session["equipment_snapshot"] or "{}")
            depth = INTERACTIVE_DIG_MAX_DEPTH if stage.get("type") == "final" else int(session["depth"]) + int(choice.get("depth", 0))
            choice_coins = int(choice.get("coins", 0))
            if choice_coins > 0:
                choice_coins = scale_interactive_reward(choice_coins)
            effects = list(snapshot.get("used_effects") or [])
            medkit_message = ""
            if choice_coins < 0 and _use_interactive_medkit(
                db,
                game,
                0,
                user["id"],
                snapshot,
                effects,
                "Аптечка: потеря котоинов в событии отменена",
            ):
                choice_coins = 0
                medkit_message = " Аптечка отменила потерю котоинов."
            coins = max(0, int(session["temporary_coins"]) + choice_coins)
            durability = int(session["durability"])
            merchant_message = ""
            durability_delta = int(choice.get("durability", 0))
            if durability_delta:
                durability = max(0, min(INTERACTIVE_DIG_DURABILITY, durability + durability_delta))
            if choice.get("merchant"):
                merchant_message = " Купец теперь ждёт снаружи, в сумке."
            collapsed = False
            if int(choice.get("risk", 0)) and secrets.randbelow(100) < int(choice.get("risk", 0)):
                if _use_interactive_medkit(
                    db,
                    game,
                    0,
                    user["id"],
                    snapshot,
                    effects,
                    "Аптечка: повреждение от риска отменено",
                ):
                    medkit_message = " Аптечка спасла прочность."
                else:
                    durability -= 1
                collapsed = durability <= 0
            snapshot["used_effects"] = effects
            if choice.get("settle") or stage.get("type") == "final" or collapsed:
                db.update_interactive_dig_session(
                    session["id"],
                    depth=depth,
                    durability=max(0, durability),
                    temporary_coins=coins,
                    equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
                )
                finished = db.get_interactive_dig_session(session["id"])
                message = _settle_interactive_manual(db, game, user, finished, datetime.now(timezone.utc), collapsed=collapsed)
                return {"ok": True, "finished": True, "message": message, "state": _state(db, user["id"])}
            if int(choice.get("chance", 0)):
                snapshot["chance_bonus"] = float(snapshot.get("chance_bonus", 0.0)) + int(choice.get("chance", 0))
            next_stage = generate_dig_stage(depth + 1, str(snapshot.get("mine_key") or "old_mine"))
            db.update_interactive_dig_session(
                session["id"],
                depth=depth,
                durability=durability,
                temporary_coins=coins,
                cells_json=json.dumps(next_stage, ensure_ascii=False),
                used_cells_json="[]",
                equipment_snapshot=json.dumps(snapshot, ensure_ascii=False),
            )
            return {"ok": True, "message": f"Выбор принят: {choice.get('label', 'действие')}.{merchant_message}{medkit_message}", "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/interactive/exit")
def miniapp_interactive_exit(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            _ensure_mine_not_blocked(db, user["id"])
            session = db.get_active_interactive_dig_session(user["id"])
            if not session:
                raise HTTPException(400, "Активной вылазки нет.")
            message = _settle_interactive_manual(db, game, user, session, datetime.now(timezone.utc), collapsed=False)
            return {"ok": True, "finished": True, "message": message, "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/dig")
def miniapp_dig_manual(
    response: Response,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            _ensure_mine_not_blocked(db, user["id"])

            now = datetime.now(timezone.utc)
            session = db.get_dig_session(user["id"])
            if not session:
                _begin_manual(db, game, user, now)
                session = db.get_dig_session(user["id"])

            meter = int(session["depth"]) + 1
            data = json.loads(session["route_data"])
            effects = json.loads(session["used_effects"] or "[]")
            if data.get("forcedDepth"):
                message = _finish_manual(db, game, user, session, 10, now)
                response.headers["X-Miniapp-Dig-Finished"] = "1"
                return {"ok": True, "finished": True, "meter": 10, "chance": 100, "message": message, "state": _state(db, user["id"])}

            items = _items_map(db, user["id"])
            chance = min(
                95.0,
                float(game.DIG_SUCCESS_CHANCES[meter - 1])
                + float(data["routeChance"])
                + (10 if data.get("flashlight") else 0)
                + int(data.get("shovelBonus", 0))
                + int(data.get("rankChance", 0)),
            )
            success = secrets.randbelow(10000) < int(chance * 100)
            if not success and items.get("drill", 0) > 0 and db.consume_dig_item(0, user["id"], "drill"):
                success = True
                effects.append(f"Бур: пробит {meter}-й метр")
            if not success and items.get("dynamite", 0) > 0 and db.consume_dig_item(0, user["id"], "dynamite"):
                success = True
                effects.append(f"Динамит: пробит {meter}-й метр")

            if success and meter < 10:
                db.save_dig_session(
                    user["id"], meter, int(session["luck_before"]), session["route_key"],
                    session["route_data"], json.dumps(effects), session["started_at"],
                )
                return {
                    "ok": True,
                    "finished": False,
                    "meter": meter,
                    "chance": chance,
                    "message": f"Метр {meter} пройден. Копайте дальше.",
                    "state": _state(db, user["id"]),
                }

            depth = meter if success else meter - 1
            if not success and depth == 0 and items.get("insurance", 0) > 0 and db.consume_dig_item(0, user["id"], "insurance"):
                depth = 1
                effects.append("Страховка: первый метр засчитан")
            db.save_dig_session(
                user["id"], int(session["depth"]), int(session["luck_before"]), session["route_key"],
                session["route_data"], json.dumps(effects), session["started_at"],
            )
            session = db.get_dig_session(user["id"])
            message = _finish_manual(db, game, user, session, max(0, depth), now)
            response.headers["X-Miniapp-Dig-Finished"] = "1"
            return {"ok": True, "finished": True, "meter": max(0, depth), "chance": chance, "message": message, "state": _state(db, user["id"])}
        finally:
            db.close()
