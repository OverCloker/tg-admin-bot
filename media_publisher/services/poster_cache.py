from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from ..providers.base import Metadata


class PosterCache:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    async def cache(self, metadata: Metadata) -> Metadata:
        url = metadata.poster_url or metadata.season_poster_url
        if not url:
            return metadata
        suffix = Path(urlsplit(url).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        target = self.directory / (hashlib.sha256(url.encode()).hexdigest() + suffix)
        if not target.is_file() or target.stat().st_size == 0:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    response.raise_for_status()
                    data = await response.read()
            if not data:
                raise RuntimeError("Источник вернул пустой постер.")
            target.write_bytes(data)
        metadata.poster_path = str(target)
        return metadata
