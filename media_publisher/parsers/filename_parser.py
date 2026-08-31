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
_DUB_BRACKET = re.compile(r"[\[(]([^\[\]()]+?)(?:\s+\d{1,2}\+)?[\])]\s*$")


def _clean_title(raw: str) -> str:
    value = re.sub(r"[._]+", " ", raw)
    value = re.sub(r"\s+", " ", value).strip(" -_")
    value = re.sub(r"(?i)\b(?:s\s*[-_]?\s*season|с\s*[-_]?\s*сезон)\b.*$", "", value).strip(" -_")
    value = re.sub(r"(?i)\b(?:season|сезон)\s*\d+.*$", "", value).strip(" -_")
    return value or "Без названия"


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
    dub_match = _DUB_BRACKET.search(stem)
    dub = dub_match.group(1).strip() if dub_match else None
    if dub and _QUALITY.fullmatch(dub):
        dub = None

    title_source = stem
    if match:
        title_source = stem[: match.start()]
    elif season is not None:
        title_source = re.split(r"(?i)\b(?:season|сезон|s)\b", stem, maxsplit=1)[0]
    title = _clean_title(title_source)
    tags = [item.group(1) for item in _QUALITY.finditer(stem)]
    warning = None
    if season is None or episode is None:
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
    )

