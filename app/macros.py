"""Validated, deliberately small command language for per-chat macros."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .db import normalize_trigger


@dataclass(frozen=True)
class MacroAction:
    kind: str
    target: str = ""
    duration: str = ""
    reason: str = ""
    text: str = ""


_QUIET = re.compile(
    r"^затихни\s+(@[A-Za-z0-9_]{5,32}|[1-9]\d{0,18})"
    r"(?:\s+(\d{1,5}\s*(?:м|мин|ч|час|д|день|m|h|d)?))?"
    r"(?:\s*-\s*(.{1,200}))?$",
    re.IGNORECASE,
)


def validate_macro_phrase(phrase: str) -> str:
    normalized = normalize_trigger(phrase)
    if not normalized or len(normalized) > 120 or normalized.startswith("/"):
        raise ValueError("Фраза макроса должна содержать от 1 до 120 символов и не начинаться с /.")
    if normalized.startswith(("затихни", "трещи", "погода", "правила")):
        raise ValueError("Фраза совпадает с командой бота. Выбери другое название макроса.")
    return normalized


def parse_macro_action(action: str, *, has_media: bool = False) -> MacroAction:
    value = action.strip()
    if not value:
        if has_media:
            return MacroAction("media")
        raise ValueError("Добавь действие или вложение.")
    if value.casefold().startswith("затихни"):
        match = _QUIET.fullmatch(value)
        if not match:
            raise ValueError("Формат мута: затихни @username 30м - причина (можно указать ID вместо ника).")
        if match.group(1).isdigit() and int(match.group(1)) > 2**63 - 1:
            raise ValueError("Некорректный Telegram ID пользователя.")
        return MacroAction("quiet", target=match.group(1), duration=(match.group(2) or "1ч").replace(" ", ""), reason=match.group(3) or "")
    if value.casefold().startswith("сообщение:"):
        text = value.split(":", 1)[1].strip()
        if not text:
            raise ValueError("После «сообщение:» нужен текст.")
        return MacroAction("message", text=text)
    raise ValueError("Разрешены действия «затихни @ник или ID [срок]» и «сообщение: текст»; либо одно вложение.")
