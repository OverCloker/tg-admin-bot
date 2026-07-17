"""Telegram Mini App for one-meter mine runs."""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl
from aiogram import Bot
from aiogram.types import LabeledPrice
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from .config import load_config
from .db import Database
from .miniapp_ui import MINI_APP_HTML as MINI_APP_UI_HTML

router = APIRouter()
DIG_LOCK = Lock()


class TicketPick(BaseModel):
    cell: int = Field(ge=0, le=8)


class SuperTicketPick(BaseModel):
    cell: int = Field(ge=0, le=80)


class ShopPurchase(BaseModel):
    item_key: str = Field(min_length=1, max_length=64)


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


def _db() -> Database:
    db = Database(load_config().db_path)
    db.init()
    # The legacy mine helpers in bot.py use its shared DB handle. The API
    # process has its own request-scoped connection, so bind it before using
    # those helpers from Mini App endpoints.
    from . import bot as game
    game.db = db
    return db


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
        return {"id": int(tg_user["id"]), "username": tg_user.get("username"),
                "full_name": " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or str(tg_user["id"])}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Данные пользователя Telegram устарели.") from exc


def _state(db: Database, user_id: int) -> dict[str, Any]:
    from . import bot as game
    player = db.get_dig_player(0, user_id)
    if not player:
        return {"registered": False, "userId": user_id}
    session = db.get_dig_session(user_id)
    now = datetime.now(timezone.utc)
    cooldown = None
    if player.last_dig_at and not session:
        cooldown_at = datetime.fromisoformat(player.last_dig_at) + game.user_dig_cooldown(user_id)
        if cooldown_at > now:
            cooldown = cooldown_at.isoformat()
    progress = db.get_dig_progress(user_id)
    return {"registered": True, "userId": user_id,
            "name": game.dig_player_name(player.username, player.full_name),
            "coins": player.coins,
            "luck": game.refreshed_dig_luck(user_id, player.luck, player.last_luck_at, now),
            "totalDepth": player.total_depth, "record": player.best_session_depth,
            "level": progress["level"], "xp": progress["xp"], "streak": progress["streak"],
            "sessionDepth": int(session["depth"]) if session else 0, "inSession": bool(session),
            "cooldownUntil": cooldown,
            "items": {x.item_key: x.quantity for x in db.list_dig_items(0, user_id)},
            "goldenTickets": db.get_dig_item_quantity(0, user_id, "golden_ticket"),
            "ticketGame": _ticket_public(db, user_id),
            "superPasses": db.get_dig_item_quantity(0, user_id, "super_game_pass"),
            "superGame": _super_ticket_public(db, user_id),
            "superRewards": {
                "mute30": db.get_dig_item_quantity(0, user_id, "super_mute30"),
                "tag": db.get_dig_item_quantity(0, user_id, "super_tag"),
            }}


def _begin(db: Database, game: Any, user: dict[str, Any], now: datetime) -> None:
    uid = user["id"]
    player = db.get_dig_player(0, uid)
    if not player:
        raise HTTPException(400, "Сначала зарегистрируйтесь в игре.")
    if player.last_dig_at:
        next_dig = datetime.fromisoformat(player.last_dig_at) + game.user_dig_cooldown(uid)
        if now < next_dig:
            left = max(1, int((next_dig - now).total_seconds()))
            raise HTTPException(429, f"Лопата отдыхает еще {left // 3600} ч {(left % 3600) // 60} мин.")
    route_key, route = game.dig_route(uid)
    luck = game.refreshed_dig_luck(uid, player.luck, player.last_luck_at, now)
    if luck < game.DIG_LUCK_COST:
        raise HTTPException(400, f"Недостаточно удачи: нужно {game.DIG_LUCK_COST}, сейчас {luck}.")
    items = game.dig_items_map(0, uid)
    helmet = items.get("helmet", 0) > 0 and db.consume_dig_item(0, uid, "helmet")
    shovel = items.get("shovel", 0) > 0 and db.consume_dig_item(0, uid, "shovel")
    flashlight = items.get("flashlight", 0) > 0 and db.consume_dig_item(0, uid, "flashlight")
    route_name, route_chance, route_coins, route_artifacts, route_collapse, _ = route
    data = {"routeName": route_name, "routeChance": route_chance, "routeCoins": route_coins,
            "routeArtifacts": route_artifacts, "routeCollapse": route_collapse,
            "luckForChance": min(100, luck + (5 if helmet else 0)), "luckAfter": luck - game.DIG_LUCK_COST,
            "helmet": helmet, "shovel": shovel, "flashlight": flashlight}
    text = now.isoformat(timespec="seconds")
    db.set_dig_luck(0, uid, data["luckAfter"], text)
    db.save_dig_session(uid, 0, luck, route_key, json.dumps(data), json.dumps([]), text)


def _finish(db: Database, game: Any, user: dict[str, Any], session: dict[str, Any], depth: int, now: datetime) -> str:
    uid = user["id"]
    data = json.loads(session["route_data"])
    effects = json.loads(session["used_effects"] or "[]")
    collapse = max(0, int(max(0, 100 - data["luckForChance"]) * data["routeCollapse"]))
    if data["shovel"]:
        collapse //= 2
    lost = 0
    if depth and collapse and secrets.randbelow(100) < collapse:
        if db.consume_dig_item(0, uid, "safe"):
            effects.append("Сейф: обвал остановлен")
        else:
            lost = 1 + secrets.randbelow(depth)
            depth = max(0, depth - lost)
    coins = max(1, int(game.dig_coin_reward(depth) * data["routeCoins"] + 0.9999))
    coins, event = game.dig_random_event(depth, coins)
    artifact_coins, artifact = game.find_dig_artifact(0, uid, depth, game.dig_items_map(0, uid), max(0, int((data["routeArtifacts"] - 1) * 10)))
    coins = game.apply_premium_coin_bonus(uid, coins + artifact_coins, effects)
    text = now.isoformat(timespec="seconds")
    db.update_dig_player_after_dig(0, uid, user.get("username"), user["full_name"], coins, depth, depth, data["luckAfter"], text, text)
    progress = db.update_dig_progress(uid, 5 + depth * 10, depth > 0, session["route_key"])
    game.update_dig_contracts(uid, depth, coins, artifact is not None)
    expedition = db.add_dig_expedition_progress(0, uid, now.date().isoformat(), depth, game.DIG_EXPEDITION_TARGET)
    if expedition["completed"]:
        db.reward_dig_expedition(0, now.date().isoformat(), game.DIG_EXPEDITION_REWARD)
    ticket_found = game.find_golden_ticket(depth)
    if ticket_found:
        db.add_dig_item(0, uid, "golden_ticket", 1)
    db.clear_dig_session(uid)
    lines = [f"Вылазка завершена: {depth} м", f"+{coins} котоинов", f"Уровень {progress['level']}, XP {progress['xp']}"]
    if lost:
        lines.append(f"Обвал забрал {lost} м")
    if event:
        lines.append(event)
    if artifact:
        lines.append(artifact)
    if ticket_found:
        lines.append("Золотой билет найден! Откройте его в игре Mini App.")
    return "\n".join(lines)


@router.get("/miniapp", response_class=HTMLResponse)
def miniapp_page() -> str:
    return MINI_APP_UI_HTML


@router.get("/miniapp/shop-bg.png")
def miniapp_shop_background() -> FileResponse:
    return FileResponse(Path(__file__).with_name("shop-bg.png"), media_type="image/png")


def _shop_catalog(db: Database, user_id: int) -> dict[str, Any]:
    from . import bot as game

    items = game.dig_items_map(0, user_id)
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
            name, price, description = item
            products.append(
                {
                    "key": item_key,
                    "name": name,
                    "price": price,
                    "description": description,
                    "quantity": items.get(item_key, 0),
                    "owned": item_key in game.DIG_PERMANENT_ITEMS and items.get(item_key, 0) > 0,
                    "requirement": game.DIG_ITEM_REQUIREMENTS.get(item_key),
                    "canBuy": not game.dig_purchase_error(items, item_key),
                }
            )
        if products:
            categories.append({"key": category_key, "title": title, "items": products})
    return {"coins": db.get_dig_player(0, user_id).coins, "categories": categories}


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
            items = game.dig_items_map(0, user["id"])
            purchase_error = game.dig_purchase_error(items, payload.item_key)
            if purchase_error:
                raise HTTPException(400, purchase_error)
            status = db.purchase_dig_item(
                0,
                user["id"],
                payload.item_key,
                int(item[1]),
                quantity=1,
                unique=payload.item_key in game.DIG_PERMANENT_ITEMS,
            )
            if status == "owned":
                raise HTTPException(400, "Это постоянное улучшение уже куплено.")
            if status == "no_coins":
                raise HTTPException(400, "Не хватает котоинов.")
            return {"ok": True, "item": payload.item_key, "state": _state(db, user["id"]), "shop": _shop_catalog(db, user["id"])}
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


@router.post("/miniapp/mine/register")
def miniapp_register(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    db = _db()
    try:
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
            positions = secrets.SystemRandom().sample(range(81), 11)
            for cell, prize in zip(positions[:10], (50, 75, 100, 125, 150, 175, 200, 225, 250, 250)):
                cells[cell] = prize
            cells[positions[10]] = secrets.choice(("super:mute30", "super:tag", "super:coins500"))
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
            description="10 попыток, 10 денежных призов и один сундук с особой наградой.",
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
            else:
                db.save_super_ticket_game(user["id"], game["cells_json"], json.dumps(opened), attempts_left, game["created_at"])
                next_game = _super_ticket_public(db, user["id"])
            return {"ok": True, "cell": payload.cell, "coins": reward if isinstance(reward, int) else 0,
                    "reward": reward_key, "attemptsLeft": attempts_left, "game": next_game,
                    "state": _state(db, user["id"])}
        finally:
            db.close()


@router.post("/miniapp/mine/dig")
def miniapp_dig(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    user = _telegram_user(x_telegram_init_data)
    with DIG_LOCK:
        db = _db()
        try:
            from . import bot as game
            now = datetime.now(timezone.utc)
            session = db.get_dig_session(user["id"])
            if not session:
                _begin(db, game, user, now)
                session = db.get_dig_session(user["id"])
            meter = int(session["depth"]) + 1
            data = json.loads(session["route_data"])
            chance = min(95.0, float(game.DIG_SUCCESS_CHANCES[meter - 1]) + float(data["routeChance"]) + (10 if data["flashlight"] else 0) + game.dig_permanent_shovel_bonus(game.dig_items_map(0, user["id"])))
            success = secrets.randbelow(10000) < int(chance * 100)
            if success and meter < 10:
                db.save_dig_session(user["id"], meter, int(session["luck_before"]), session["route_key"], session["route_data"], session["used_effects"], session["started_at"])
                return {"ok": True, "finished": False, "meter": meter, "chance": chance, "message": f"Метр {meter} пройден. Копайте дальше.", "state": _state(db, user["id"])}
            depth = meter if success else meter - 1
            message = _finish(db, game, user, session, max(0, depth), now)
            return {"ok": True, "finished": True, "meter": max(0, depth), "chance": chance, "message": message, "state": _state(db, user["id"])}
        finally:
            db.close()


MINI_APP_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Шахта</title><script src="https://telegram.org/js/telegram-web-app.js"></script><style>body{font-family:system-ui;background:#0b111b;color:#f4f7fb;padding:16px}main{max-width:520px;margin:auto}.panel,.stat{background:#172434;border:1px solid #26394d;border-radius:14px;padding:14px;margin-top:12px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stat b{display:block;font-size:19px;margin-top:4px}.muted{color:#9ba8b8}.depth{text-align:center;font-size:44px;font-weight:800;padding:18px}.meter{height:10px;background:#0e1722;border-radius:9px;overflow:hidden}.fill{height:100%;background:#45b9ef}.btn{width:100%;border:0;border-radius:12px;padding:15px;margin-top:12px;background:#268bd2;color:white;font-size:18px;font-weight:700}.notice{white-space:pre-line}</style></head><body><main><h1>⛏️ Шахта</h1><div class="muted" id="name">Загрузка...</div><div id="content"></div></main><script>const tg=window.Telegram&&window.Telegram.WebApp;if(tg){tg.ready();tg.expand()}const H=()=>({'X-Telegram-Init-Data':tg?tg.initData:''});let s=null,busy=false;async function api(p,o={}){let r=await fetch(p,Object.assign({},o,{headers:Object.assign({},H(),o.headers||{}, {'Content-Type':'application/json'})}));let d=await r.json().catch(()=>({detail:'Ошибка сервера'}));if(!r.ok)throw Error(d.detail||'Ошибка запроса');return d}function render(){let c=document.getElementById('content');if(!s)return;if(!s.registered){c.innerHTML='<section class="panel"><div class="depth">⛏️</div><div>Зарегистрируйтесь, чтобы начать общую шахту. Прогресс и котоины сохраняются и в боте.</div><button class="btn" onclick="reg()">Начать игру</button></section>';return}document.getElementById('name').textContent=s.name;let d=s.sessionDepth||0;let disabled=s.cooldownUntil&&!s.inSession;c.innerHTML='<div class="stats"><div class="stat">🪙<b>'+s.coins+'</b></div><div class="stat">🍀<b>'+s.luck+'/100</b></div><div class="stat">🏆<b>'+s.record+' м</b></div></div><section class="panel"><div class="muted">Текущая вылазка</div><div class="depth">'+d+'/10 м</div><div class="meter"><div class="fill" style="width:'+(d*10)+'%"></div></div><button class="btn" '+(disabled?'disabled':'')+' onclick="dig()">⛏️ Копать следующий метр</button><div class="muted">'+(disabled?'Кулдаун: '+new Date(s.cooldownUntil).toLocaleString():'Каждое нажатие проверяет один метр. Шансы те же, что в боте.')+'</div></section><section class="panel">Уровень '+s.level+' · XP '+s.xp+' · серия '+s.streak+'</section>'}async function load(){try{s=await api('/miniapp/mine');render()}catch(e){content.innerHTML='<section class="panel">'+e.message+'</section>'}}async function reg(){try{s=await api('/miniapp/mine/register',{method:'POST'});render()}catch(e){alert(e.message)}}async function dig(){if(busy)return;busy=true;try{let d=await api('/miniapp/mine/dig',{method:'POST'});s=d.state;render();let n=document.createElement('section');n.className='panel notice';n.textContent=d.message;content.prepend(n)}catch(e){alert(e.message);load()}finally{busy=false}}load();</script></body></html>"""
