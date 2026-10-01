"""Validated, deliberately small command language for per-chat macros."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .db import normalize_trigger


@dataclass(frozen=True)
class MacroAction:
    kind: str
    target: str = ""
    targets: tuple[str, ...] = ()
    duration: str = ""
    reason: str = ""
    text: str = ""


_QUIET = re.compile(
    r"^затихни\s+(@[A-Za-z0-9_]{5,32}|[1-9]\d{0,18})"
    r"(?:\s+(\d{1,5}\s*(?:м|мин|ч|час|д|день|m|h|d)?))?"
    r"(?:\s*-\s*(.{1,200}))?$",
    re.IGNORECASE,
)
_TARGET = re.compile(r"(?:@[A-Za-z0-9_]{5,32}|[1-9]\d{0,18})\Z")
_BATCH_QUIET = re.compile(
    r"^затихни(?:\s+(\d{1,5}\s*(?:м|мин|ч|час|д|день|m|h|d)?))?"
    r"(?:\s*-\s*(.{1,200}))?$",
    re.IGNORECASE,
)
_ANNOUNCE = re.compile(r"^(позвать|оповестить)\s*-\s*(.{1,200})$", re.IGNORECASE)


def _macro_targets(lines: list[str]) -> tuple[str, ...]:
    targets = tuple(lines)
    if not 1 <= len(targets) <= 10:
        raise ValueError("Укажи от 1 до 10 человек, по одному @нику или Telegram ID на строку.")
    if any(not _TARGET.fullmatch(target) or (target.isdigit() and int(target) > 2**63 - 1) for target in targets):
        raise ValueError("Каждая цель макроса должна быть @ником или корректным Telegram ID.")
    if len({target.casefold() for target in targets}) != len(targets):
        raise ValueError("Не повторяй одного адресата в макросе.")
    return targets


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
        if "\n" in value:
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            match = _BATCH_QUIET.fullmatch(lines[0])
            if not match:
                raise ValueError("Массовый мут: первая строка «затихни 10 - причина», затем от 1 до 10 @ников или ID, каждый с новой строки.")
            targets = _macro_targets(lines[1:])
            return MacroAction("quiet", targets=targets, duration=(match.group(1) or "1ч").replace(" ", ""), reason=match.group(2) or "")
        match = _QUIET.fullmatch(value)
        if not match:
            raise ValueError("Формат мута: затихни @username 30м - причина (можно указать ID вместо ника).")
        if match.group(1).isdigit() and int(match.group(1)) > 2**63 - 1:
            raise ValueError("Некорректный Telegram ID пользователя.")
        return MacroAction("quiet", target=match.group(1), duration=(match.group(2) or "1ч").replace(" ", ""), reason=match.group(3) or "")
    if value.casefold().startswith(("позвать", "оповестить")):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        match = _ANNOUNCE.fullmatch(lines[0])
        if not match:
            raise ValueError("Формат: «позвать - куда» или «оповестить - о чём», затем @ники или ID с новой строки.")
        return MacroAction(
            "call" if match.group(1).casefold() == "позвать" else "notify",
            targets=_macro_targets(lines[1:]), text=match.group(2).strip(),
        )
    if value.casefold().startswith("сообщение:"):
        text = value.split(":", 1)[1].strip()
        if not text:
            raise ValueError("После «сообщение:» нужен текст.")
        return MacroAction("message", text=text)
    raise ValueError("Разрешены действия «затихни», «позвать - куда», «оповестить - о чём», «сообщение: текст»; либо одно вложение.")
