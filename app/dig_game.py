from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


INTERACTIVE_DIG_SUCCESS_CHANCES = [90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 1.0]
INTERACTIVE_DIG_MAX_DEPTH = 10
INTERACTIVE_DIG_MIN_CELLS_PER_METER = 3
INTERACTIVE_DIG_MAX_CELLS_PER_METER = 7
INTERACTIVE_DIG_CELLS_PER_METER = 5
INTERACTIVE_DIG_DURABILITY = 3
INTERACTIVE_DIG_REWARD_SCALE_PERCENT = 42

MINE_RESOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "res_stone": {"title": "Каменная крошка", "emoji": "🪨", "base": 8, "min": 4, "max": 14, "rarity": "common"},
    "res_coal": {"title": "Уголь", "emoji": "⚫", "base": 14, "min": 8, "max": 22, "rarity": "common"},
    "res_iron": {"title": "Железная руда", "emoji": "⛓", "base": 24, "min": 14, "max": 38, "rarity": "uncommon"},
    "res_silver": {"title": "Серебряная жила", "emoji": "🥈", "base": 42, "min": 26, "max": 64, "rarity": "rare"},
    "res_crystal": {"title": "Осколок кристалла", "emoji": "💎", "base": 70, "min": 45, "max": 105, "rarity": "epic"},
    "res_fossil": {"title": "Древний отпечаток", "emoji": "🦴", "base": 55, "min": 34, "max": 82, "rarity": "rare"},
    "res_ember": {"title": "Пламенная руда", "emoji": "🔥", "base": 80, "min": 50, "max": 120, "rarity": "epic"},
    "res_glow_moss": {"title": "Светящийся мох", "emoji": "🌿", "base": 30, "min": 16, "max": 48, "rarity": "uncommon"},
}

MINE_RESOURCE_ORDER = [
    "res_stone",
    "res_coal",
    "res_iron",
    "res_silver",
    "res_crystal",
    "res_fossil",
    "res_ember",
    "res_glow_moss",
]

MINE_TYPES = [
    {
        "key": "old_mine",
        "title": "Старая шахта",
        "emoji": "⛏",
        "description": "Ровная классика: земля, уголь и понятный риск.",
        "chance_bonus": 0.0,
        "reward_bonus": 0,
        "hard_bias": 0,
        "event_bonus": 0,
    },
    {
        "key": "ice_cave",
        "title": "Ледяная пещера",
        "emoji": "🧊",
        "description": "Скользкие ходы: больше неизвестных слоёв, но чуть легче выйти сухим.",
        "chance_bonus": -2.0,
        "reward_bonus": 8,
        "hard_bias": 0,
        "event_bonus": 6,
    },
    {
        "key": "volcanic_tunnels",
        "title": "Вулканические тоннели",
        "emoji": "🌋",
        "description": "Жарко и опасно: больше твёрдой породы, зато награды жирнее.",
        "chance_bonus": -5.0,
        "reward_bonus": 18,
        "hard_bias": 1,
        "event_bonus": 4,
    },
    {
        "key": "mushroom_cave",
        "title": "Грибная пещера",
        "emoji": "🍄",
        "description": "Странные корни и живые тоннели: чаще попадаются события.",
        "chance_bonus": 1.0,
        "reward_bonus": 5,
        "hard_bias": 0,
        "event_bonus": 14,
    },
    {
        "key": "ancient_ruins",
        "title": "Древние руины",
        "emoji": "🏛",
        "description": "Двери, развилки и ловушки: меньше руды, больше особых комнат.",
        "chance_bonus": -3.0,
        "reward_bonus": 15,
        "hard_bias": 0,
        "event_bonus": 18,
    },
    {
        "key": "crystal_mine",
        "title": "Кристальная шахта",
        "emoji": "💎",
        "description": "Редкая глубина: руды богаче, но десятый метр почти легенда.",
        "chance_bonus": -7.0,
        "reward_bonus": 28,
        "hard_bias": 1,
        "event_bonus": 8,
    },
]

MINE_TYPES_BY_KEY = {item["key"]: item for item in MINE_TYPES}


EVENT_ROOMS: dict[str, dict[str, Any]] = {
    "merchant": {
        "emoji": "🧑‍🌾",
        "title": "Подземный торговец",
        "text": "Кот встретил торговца с подозрительно чистыми сапогами. Он скупает руду по текущей цене.",
        "choices": [
            {"key": "sell_ore", "label": "Продать руду", "merchant": True, "next": "cells"},
            {"key": "trade", "label": "Взять припасы", "coins": 3, "durability": 1, "next": "cells"},
            {"key": "ignore", "label": "Идти дальше", "coins": 0, "next": "cells"},
        ],
    },
    "lost_cat": {
        "emoji": "🐈",
        "title": "Потерявшийся кот",
        "text": "В темноте мяукнул чужой шахтёр.",
        "choices": [
            {"key": "help", "label": "Помочь коту", "coins": 12, "durability": 1, "next": "cells"},
            {"key": "share", "label": "Поделиться добычей", "coins": -5, "chance": 5, "next": "cells"},
        ],
    },
    "cart": {
        "emoji": "🛒",
        "title": "Вагонетка с развилкой",
        "text": "Рельсы уходят в две стороны. Одна точно шумит богаче.",
        "choices": [
            {"key": "safe", "label": "Тихий путь", "coins": 8, "next": "cells"},
            {"key": "fast", "label": "Шумный путь", "coins": 22, "risk": 35, "depth": 1, "next": "cells"},
        ],
    },
    "lake": {
        "emoji": "🌊",
        "title": "Подземное озеро",
        "text": "Вода чистая, но дна не видно.",
        "choices": [
            {"key": "rest", "label": "Передохнуть", "durability": 1, "next": "cells"},
            {"key": "dive", "label": "Нырнуть", "coins": 25, "risk": 45, "next": "cells"},
        ],
    },
    "door": {
        "emoji": "🚪",
        "title": "Древняя дверь",
        "text": "На двери выцарапан котолапый замок.",
        "choices": [
            {"key": "open", "label": "Открыть", "coins": 35, "risk": 30, "next": "cells"},
            {"key": "around", "label": "Обойти", "coins": 5, "next": "cells"},
        ],
    },
    "gas": {
        "emoji": "🟢",
        "title": "Газовый карман",
        "text": "Воздух стал тяжёлым. Кирка просит осторожности.",
        "choices": [
            {"key": "vent", "label": "Проветрить", "coins": 0, "next": "cells"},
            {"key": "rush", "label": "Рвануть глубже", "coins": 15, "risk": 55, "depth": 1, "next": "cells"},
        ],
    },
    "nest": {
        "emoji": "🪺",
        "title": "Гнездо существ",
        "text": "Что-то шуршит в породе и охраняет блестяшки.",
        "choices": [
            {"key": "sneak", "label": "Тихо обойти", "coins": 7, "next": "cells"},
            {"key": "grab", "label": "Схватить блеск", "coins": 30, "risk": 40, "next": "cells"},
        ],
    },
    "fork": {
        "emoji": "↔️",
        "title": "Развилка",
        "text": "Один ход ведёт ниже, второй — к безопасному подъёму.",
        "choices": [
            {"key": "deeper", "label": "Продолжить глубже", "chance": 3, "next": "cells"},
            {"key": "claim", "label": "Забрать добычу", "settle": True},
        ],
    },
    "ore_vein": {
        "emoji": "✨",
        "title": "Жила руды",
        "text": "Жила уходит в стену. Можно снять сливки или рискнуть ещё ударом.",
        "choices": [
            {"key": "collect", "label": "Снять руду", "coins": 20, "next": "cells"},
            {"key": "develop", "label": "Разрабатывать", "coins": 18, "risk": 28, "repeat": 45, "next": "event"},
        ],
    },
    "unstable": {
        "emoji": "⏱",
        "title": "Нестабильный тоннель",
        "text": "Порода трещит. Решение нужно принимать быстро.",
        "choices": [
            {"key": "brace", "label": "Укрепить", "durability": 1, "next": "cells"},
            {"key": "dash", "label": "Проскочить", "coins": 28, "risk": 50, "depth": 1, "next": "cells"},
        ],
    },
}


@dataclass(frozen=True)
class DigCellSpec:
    key: str
    title: str
    emoji: str
    chance_modifier: float
    reward_multiplier: float


DIG_CELL_SPECS: dict[str, DigCellSpec] = {
    "normal": DigCellSpec("normal", "обычный грунт", "🟫", 0.0, 1.0),
    "ore": DigCellSpec("ore", "рудная жила", "✨", -3.0, 1.35),
    "hard": DigCellSpec("hard", "твёрдая порода", "🪨", -8.0, 1.6),
    "roots": DigCellSpec("roots", "странные корни", "🌿", 0.0, 1.0),
    "unknown": DigCellSpec("unknown", "неизвестный слой", "❓", 0.0, 1.0),
}


def clamp_chance(value: float) -> float:
    return max(1.0, min(100.0, float(value)))


def cell_public_emoji(cell: Mapping[str, Any]) -> str:
    return DIG_CELL_SPECS.get(str(cell.get("kind")), DIG_CELL_SPECS["unknown"]).emoji


def mine_type_for_total_depth(total_depth: int) -> dict[str, Any]:
    index = max(0, min(len(MINE_TYPES) - 1, int(total_depth) // 10))
    return MINE_TYPES[index]


def mine_type_for_key(key: str | None) -> dict[str, Any]:
    return MINE_TYPES_BY_KEY.get(str(key or ""), MINE_TYPES[0])


def generate_dig_cells(depth: int, rng: random.Random | None = None, mine_key: str = "old_mine") -> list[dict[str, Any]]:
    """Generate 3-7 public cells for one mine meter.

    Rules:
    - at least two normal cells;
    - hard rock is limited by row size;
    - increased-reward cells are limited by row size;
    - unknown is optional and resolves after click.
    """
    rng = rng or random.SystemRandom()
    depth = max(1, min(INTERACTIVE_DIG_MAX_DEPTH, int(depth)))
    mine = mine_type_for_key(mine_key)
    cell_count = rng.randint(INTERACTIVE_DIG_MIN_CELLS_PER_METER, INTERACTIVE_DIG_MAX_CELLS_PER_METER)

    if depth <= 3:
        pool = ["normal", "normal", "normal", "ore", "roots", "unknown", "normal"]
    elif depth <= 7:
        pool = ["normal", "normal", "ore", "hard", "roots", "unknown", "normal"]
    else:
        pool = ["normal", "normal", "ore", "hard", "roots", "unknown", "ore"]
    rng.shuffle(pool)
    cells = pool[:cell_count]

    if mine["key"] == "ice_cave":
        replace_one(cells, rng, "roots", "unknown")
    elif mine["key"] == "volcanic_tunnels":
        replace_one(cells, rng, "unknown", "hard")
    elif mine["key"] == "mushroom_cave":
        replace_one(cells, rng, "ore", "roots")
    elif mine["key"] == "ancient_ruins":
        replace_one(cells, rng, "ore", "unknown")
    elif mine["key"] == "crystal_mine":
        replace_one(cells, rng, "roots", "ore")
        if int(mine.get("hard_bias", 0)) and "hard" not in cells:
            replace_one(cells, rng, "unknown", "hard")

    while cells.count("normal") < 2:
        replace_one(cells, rng, rng.choice([kind for kind in cells if kind != "normal"]), "normal")
    hard_limit = 1 if cell_count <= 5 else 2
    reward_limit = 2 if cell_count <= 5 else 3
    while cells.count("hard") > hard_limit:
        replace_one(cells, rng, "hard", "normal")
    while sum(1 for kind in cells if kind in {"ore", "hard"}) > reward_limit:
        replace_one(cells, rng, rng.choice([kind for kind in cells if kind in {"ore", "hard"}]), "normal")

    rng.shuffle(cells)
    return [{"kind": kind} for kind in cells]


def final_room_stage(mine_key: str = "old_mine", rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.SystemRandom()
    mine = mine_type_for_key(mine_key)
    rooms = [
        {
            "key": "chest",
            "label": "Сундук",
            "title": "Финальная комната: сундук",
            "text": "В центре комнаты стоит сундук, по крышке бегут шахтёрские искры.",
            "coins": 55,
        },
        {
            "key": "ore_deposit",
            "label": "Залежь руды",
            "title": "Финальная комната: залежь руды",
            "text": "Стена блестит так, будто её полировали жадные кроты.",
            "coins": 70,
        },
        {
            "key": "mini_boss",
            "label": "Мини-босс",
            "title": "Финальная комната: мини-босс",
            "text": "Из пыли выходит хранитель забоя. Он маленький, но с характером.",
            "coins": 90,
            "risk": 35,
        },
        {
            "key": "ancient_artifact",
            "label": "Древний артефакт",
            "title": "Финальная комната: древний артефакт",
            "text": "На постаменте лежит вещь, которую явно забыли не вчера.",
            "coins": 75,
            "artifact": True,
        },
        {
            "key": "deeper_exit",
            "label": "Глубокий выход",
            "title": "Финальная комната: выход глубже",
            "text": f"{mine['title']} открывает проход в следующий пласт шахт.",
            "coins": 45,
            "unlock": True,
        },
    ]
    room = rng.choice(rooms)
    return {
        "type": "final",
        "emoji": mine["emoji"],
        "title": room["title"],
        "text": room["text"],
        "choices": [
            {"key": room["key"], "label": room["label"], "coins": room["coins"], "risk": room.get("risk", 0), "settle": True},
            {"key": "claim", "label": "Забрать добычу", "coins": 35 + int(mine.get("reward_bonus", 0)), "settle": True},
        ],
    }


def replace_one(cells: list[str], rng: random.Random, old: str, new: str) -> None:
    indexes = [index for index, kind in enumerate(cells) if kind == old]
    if indexes:
        cells[rng.choice(indexes)] = new


def generate_dig_stage(depth: int, mine_key: str = "old_mine", rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.SystemRandom()
    depth = max(1, min(INTERACTIVE_DIG_MAX_DEPTH, int(depth)))
    if depth >= INTERACTIVE_DIG_MAX_DEPTH:
        return final_room_stage(mine_key, rng)
    mine = mine_type_for_key(mine_key)
    event_chance = min(55, 8 + depth * 3 + int(mine.get("event_bonus", 0)))
    if depth in {3, 6, 9}:
        event_chance += 18
    if rng.randrange(100) < event_chance:
        return generate_event_stage(depth, mine_key, rng)
    return {"type": "cells", "cells": generate_dig_cells(depth, rng, mine_key)}


def cell_row_is_exhausted(cells: list[Mapping[str, Any]], used_cells: list[int]) -> bool:
    """Return True when a cell row has no clickable cells left."""
    cell_count = len(cells)
    if cell_count <= 0:
        return False
    used = {int(index) for index in used_cells if 0 <= int(index) < cell_count}
    return len(used) >= cell_count


def replacement_cell_stage(depth: int, mine_key: str = "old_mine", rng: random.Random | None = None) -> dict[str, Any]:
    """Generate a fresh cell row for the same meter after all choices failed."""
    depth = max(1, min(INTERACTIVE_DIG_MAX_DEPTH - 1, int(depth)))
    return {"type": "cells", "cells": generate_dig_cells(depth, rng, mine_key)}


def generate_event_stage(depth: int, mine_key: str = "old_mine", rng: random.Random | None = None, preferred: str | None = None) -> dict[str, Any]:
    rng = rng or random.SystemRandom()
    mine_key = mine_type_for_key(mine_key)["key"]
    weighted = {
        "old_mine": ["lost_cat", "cart", "fork", "ore_vein"],
        "ice_cave": ["lake", "lost_cat", "gas", "fork", "unstable"],
        "volcanic_tunnels": ["gas", "unstable", "ore_vein", "nest", "door"],
        "mushroom_cave": ["lost_cat", "nest", "lake", "ore_vein", "fork"],
        "ancient_ruins": ["door", "fork", "nest", "unstable", "ore_vein"],
        "crystal_mine": ["ore_vein", "door", "unstable", "gas"],
    }
    key = preferred if preferred in EVENT_ROOMS else rng.choice(weighted.get(mine_key, list(EVENT_ROOMS)))
    room = EVENT_ROOMS[key]
    return {
        "type": "event",
        "event": key,
        "depth": depth,
        "emoji": room["emoji"],
        "title": room["title"],
        "text": room["text"],
        "choices": room["choices"],
    }


def event_choice(stage: Mapping[str, Any], choice_key: str) -> dict[str, Any] | None:
    for choice in stage.get("choices", []):
        if choice.get("key") == choice_key:
            return dict(choice)
    return None


def resolve_cell(cell: Mapping[str, Any], rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.SystemRandom()
    kind = str(cell.get("kind") or "normal")
    if kind == "unknown":
        kind = rng.choices(
            ["normal", "ore", "hard", "roots"],
            weights=[52, 22, 10, 16],
            k=1,
        )[0]

    if kind == "roots":
        return {
            "kind": "roots",
            "resolved_kind": "roots",
            "chance_modifier": rng.randint(-4, 4),
            "reward_multiplier": round(rng.uniform(0.8, 1.5), 2),
        }

    spec = DIG_CELL_SPECS.get(kind, DIG_CELL_SPECS["normal"])
    return {
        "kind": kind,
        "resolved_kind": kind,
        "chance_modifier": spec.chance_modifier,
        "reward_multiplier": spec.reward_multiplier,
    }


def final_cell_chance(base_chance: float, bonus_chance: float, cell: Mapping[str, Any]) -> float:
    return clamp_chance(float(base_chance) + float(bonus_chance) + float(cell.get("chance_modifier", 0.0)))


def cell_reward(base_reward: int, route_multiplier: float, cell: Mapping[str, Any], coin_bonus_percent: int = 0) -> int:
    coins = int(float(base_reward) * float(route_multiplier) * float(cell.get("reward_multiplier", 1.0)) + 0.9999)
    if coin_bonus_percent:
        coins = (coins * (100 + int(coin_bonus_percent)) + 99) // 100
    return max(1, coins)


def scale_interactive_reward(coins: int) -> int:
    return max(1, (max(0, int(coins)) * INTERACTIVE_DIG_REWARD_SCALE_PERCENT + 99) // 100)


def cell_ore_units(cell: Mapping[str, Any]) -> int:
    kind = str(cell.get("resolved_kind") or cell.get("kind") or "")
    if kind == "hard":
        return 2
    if kind == "ore":
        return 1
    return 0


def mine_resource_market_bucket(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    return int(current.timestamp()) // (60 * 60)


def mine_resource_price(resource_key: str, now: datetime | None = None) -> int:
    resource = MINE_RESOURCE_CATALOG[resource_key]
    rng = random.Random(f"mine-resource-price:{resource_key}:{mine_resource_market_bucket(now)}")
    base = int(resource["base"])
    low = int(resource["min"])
    high = int(resource["max"])
    drift = rng.randint(-base // 3, base // 2)
    return max(low, min(high, base + drift))


def mine_resource_prices(now: datetime | None = None) -> dict[str, int]:
    return {key: mine_resource_price(key, now) for key in MINE_RESOURCE_ORDER}


def mined_resource_drops(
    cell: Mapping[str, Any],
    mine_key: str = "old_mine",
    depth: int = 1,
    rng: random.Random | None = None,
) -> dict[str, int]:
    rng = rng or random.SystemRandom()
    kind = str(cell.get("resolved_kind") or cell.get("kind") or "")
    mine_key = mine_type_for_key(mine_key)["key"]
    depth = max(1, min(INTERACTIVE_DIG_MAX_DEPTH, int(depth)))
    drops: dict[str, int] = {}

    def add(key: str, quantity: int = 1) -> None:
        drops[key] = drops.get(key, 0) + max(1, int(quantity))

    if kind == "hard":
        add("res_stone", 1 + (1 if depth >= 6 else 0))
        if rng.randrange(100) < 35:
            add("res_iron")
    elif kind == "ore":
        if depth <= 3:
            pool = ["res_coal", "res_iron"]
            weights = [58, 42]
        elif depth <= 6:
            pool = ["res_iron", "res_silver", "res_coal"]
            weights = [58, 25, 17]
        else:
            pool = ["res_iron", "res_silver", "res_crystal"]
            weights = [42, 35, 23]
        if mine_key == "volcanic_tunnels":
            pool.append("res_ember")
            weights.append(28)
        elif mine_key == "crystal_mine":
            pool.append("res_crystal")
            weights.append(38)
        elif mine_key == "ancient_ruins":
            pool.append("res_fossil")
            weights.append(24)
        add(rng.choices(pool, weights=weights, k=1)[0], 1)
        if depth >= 8 and rng.randrange(100) < 25:
            add(rng.choice(["res_silver", "res_crystal"]))
    elif kind == "roots":
        if rng.randrange(100) < 55:
            add("res_glow_moss")
        if mine_key in {"mushroom_cave", "ancient_ruins"} and rng.randrange(100) < 18:
            add("res_fossil")
    return drops


def resource_title(resource_key: str) -> str:
    return str(MINE_RESOURCE_CATALOG.get(resource_key, {}).get("title") or resource_key)


def resource_emoji(resource_key: str) -> str:
    return str(MINE_RESOURCE_CATALOG.get(resource_key, {}).get("emoji") or "▪️")


def resource_stack_text(resources: Mapping[str, int]) -> str:
    parts = []
    for key in MINE_RESOURCE_ORDER:
        quantity = int(resources.get(key, 0))
        if quantity > 0:
            parts.append(f"{resource_emoji(key)} {resource_title(key)} ×{quantity}")
    return ", ".join(parts)


def merchant_ore_price(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    bucket = mine_resource_market_bucket(current)
    rng = random.Random(f"mine-merchant-price:{bucket}")
    return rng.randint(10, 40)


def final_depth_bonus(depth: int, mine_key: str, rng: random.Random | None = None) -> tuple[int, str]:
    rng = rng or random.SystemRandom()
    if int(depth) < INTERACTIVE_DIG_MAX_DEPTH:
        return 0, ""
    mine = mine_type_for_key(mine_key)
    bonus = 45 + rng.randrange(36) + int(mine.get("reward_bonus", 0))
    return bonus, f"{mine['emoji']} Финальная находка: {mine['title']} раскрыла крупную награду: +{bonus} котоинов."


def collapse_payout(temporary_coins: int, protected_loss_percent: int = 0) -> tuple[int, int]:
    loss_percent = max(0, 30 - max(0, int(protected_loss_percent)))
    payout = max(0, int(int(temporary_coins) * (100 - loss_percent) / 100))
    return payout, max(0, int(temporary_coins) - payout)
