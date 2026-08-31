from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..models import MediaFileInfo
from ..parsers.filename_parser import VIDEO_EXTENSIONS, parse_filename


def scan_folder(folder: str | Path, extensions: Iterable[str] | None = None) -> list[MediaFileInfo]:
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"Папка не найдена: {root}")
    allowed = {item.lower() if item.startswith(".") else f".{item.lower()}" for item in (extensions or VIDEO_EXTENSIONS)}
    files: list[MediaFileInfo] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in allowed:
            files.append(parse_filename(path))
    return sorted(files, key=lambda item: (item.title.casefold(), item.season_number or 0, item.episode_number or 0, item.filename.casefold()))

