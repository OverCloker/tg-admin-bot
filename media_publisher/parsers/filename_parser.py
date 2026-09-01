from __future__ import annotations

import re
from pathlib import Path

from ..models import MediaFileInfo


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
_SEASON_EPISODE = re.compile(r"(?ix)(?:s(?:eason)?[ _.-]*|с(?:езон)?[ _.-]*)0*(?P<season>\d+)[ _.-]*(?:e(?:p(?:isode)?)?|с(?:ерия)?)?[ _.-]*0*(?P<episode>\d+)")
_SEASON_EPISODE_RU = re.compile(r"(?ix)\b0*(?P<season>\d+)\s*(?:сезон|season)\s*0*(?P<episode>\d+)\s*(?:серия|episode|ep)?")
_SEASON = re.compile(r"(?ix)\b(?:s(?:eason)?|с(?:езон)?)\s*0*(?P<season>\d+)\b")
_EPISODE = re.compile(r"(?ix)\b(?:e|ep|episode|серия|сер)\s*0*(?P<episode>\d+)\b")
_QUALITY = re.compile(r"(?i)\b(2160p|1440p|1080p|720p|480p|4k|web[- ]?dl|blu[- ]?ray|hdr)\b")
_AGE = re.compile(r"(?i)(?:\(|\[|\b)(?P<age>\d{1,2}\+)(?:\)|\]|\b)")
_BRACKET = re.compile(r"\[([^\]]+)\]")
_DUB_PHRASE = re.compile(
    r"(?ix)\b(?:в\s+озвучке|озвучка|озвучення|voice|dub(?:bed)?)\s*[:=-]?\s*"
    r"(?P<dub>.+?)(?=\s+(?:s(?:eason)?|сезон|e(?:p(?:isode)?)?|серия)\s*[-_. ]*\d*\b|$)"
)
_DUB_SUFFIX = re.compile(
    r"(?ix)(?P<dub>"
    r"(?:(?:украинский|український|русский|официальный|профессиональный|многоголосый|одноголосый)\s+)*"
    r"(?:дубляж|озвучка|озвучення|lostfilm|hdrezka(?:\s+studio)?|newstudio|coldfilm|alexfilm|baibako|кубик(?:\s+в\s+кубе)?|анилибрия)"
    r"(?:\s+(?:официальный|профессиональный|многоголосый|одноголосый|studio)){0,3})\s*$"
)


def _clean_title(raw: str) -> str:
    value = re.sub(r"[._]+", " ", raw)
    value = re.sub(r"\s+", " ", value).strip(" -_")
    value = re.sub(r"(?i)\b(?:s\s*[-_]?\s*season|с\s*[-_]?\s*сезон)\b.*$", "", value).strip(" -_")
    value = re.sub(r"(?i)\b(?:season|сезон)\s*\d+.*$", "", value).strip(" -_")
    value = re.sub(r"(?i)\b\d+\s*(?:season|сезон(?:а|е)?)\b.*$", "", value).strip(" -_")
    value = re.sub(r"(?i)\s*[-–—]?\s*все\s+серии\b.*$", "", value).strip(" -_")
    value = re.sub(r"(?i)\s+(?:в\s+озвучке|озвучка|озвучення|voice|dub(?:bed)?)\s*[:=-]?.*$", "", value).strip(" -_")
    return value or "Без названия"


def clean_candidate_title(raw: str) -> str:
    return _clean_title(Path(raw).stem)


def is_weak_title(title: str) -> bool:
    compact = "".join(char for char in title if char.isalnum())
    return len(compact) < 3 or compact.isdigit() or title == "Без названия"


def _clean_movie_title(stem: str) -> str:
    value = _BRACKET.sub("", stem)
    value = _DUB_PHRASE.sub("", value)
    suffix = _DUB_SUFFIX.search(value)
    if suffix:
        value = value[: suffix.start()].strip(" -_")
    value = _QUALITY.sub("", value)
    value = _AGE.sub("", value)
    # Some movie filenames contain empty S/E placeholders from export tools.
    value = re.sub(r"(?ix)\s+s\s*[-_. ]*\s*(?:e|ep)?\s*[-_. ]*$", "", value)
    return _clean_title(value)


def _normalise_dub(value: str) -> str | None:
    cleaned = re.sub(r"\s*\(\s*\d{1,2}\+\s*\)\s*$", "", value).strip(" -_")
    if not cleaned or _QUALITY.fullmatch(cleaned) or _AGE.fullmatch(cleaned):
        return None
    return cleaned


def _extract_dub(stem: str) -> str | None:
    phrase = _DUB_PHRASE.search(stem)
    if phrase:
        candidate = _normalise_dub(phrase.group("dub"))
        if candidate:
            return candidate
    for bracket in reversed(_BRACKET.findall(stem)):
        candidate = _normalise_dub(bracket)
        if candidate and not _QUALITY.search(candidate):
            return candidate
    suffix_source = _BRACKET.sub("", stem)
    suffix = _DUB_SUFFIX.search(suffix_source)
    return _normalise_dub(suffix.group("dub")) if suffix else None


def parse_filename(path: str | Path) -> MediaFileInfo:
    file_path = Path(path)
    stem = file_path.stem
    match = _SEASON_EPISODE.search(stem) or _SEASON_EPISODE_RU.search(stem)
    season = int(match.group("season")) if match else None
    episode = int(match.group("episode")) if match else None
    if season is None:
        season_match = _SEASON.search(stem)
        season = int(season_match.group("season")) if season_match else None
    if episode is None:
        episode_match = _EPISODE.search(stem)
        episode = int(episode_match.group("episode")) if episode_match else None

    quality_match = _QUALITY.search(stem)
    age_match = _AGE.search(stem)
    dub = _extract_dub(stem)

    title_source = stem
    if match:
        title_source = stem[: match.start()]
    elif season is not None:
        title_source = re.split(r"(?i)\b(?:season|сезон|s)\b", stem, maxsplit=1)[0]
    is_series = season is not None or episode is not None
    title = _clean_title(title_source) if is_series else _clean_movie_title(stem)
    tags = [item.group(1) for item in _QUALITY.finditer(stem)]
    warning = None
    if is_series and (season is None or episode is None):
        warning = "Не удалось уверенно определить сезон и серию; проверьте данные."
    return MediaFileInfo(
        path=file_path,
        filename=file_path.name,
        title=title,
        season_number=season,
        episode_number=episode,
        dub=dub,
        age_rating=age_match.group("age") if age_match else None,
        quality=quality_match.group(1) if quality_match else None,
        additional_tags=tags,
        warning=warning,
        media_type="series" if is_series else "movie",
    )
