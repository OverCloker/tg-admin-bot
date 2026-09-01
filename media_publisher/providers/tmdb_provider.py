from __future__ import annotations

import aiohttp

from .base import Metadata, MetadataProvider


class TmdbProvider(MetadataProvider):
    name = "TMDB"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        if not self.api_key:
            return []
        params = {"api_key": self.api_key, "query": title, "language": "ru-RU"}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.themoviedb.org/3/search/multi", params=params, timeout=15) as response:
                response.raise_for_status()
                payload = await response.json()
        result: list[Metadata] = []
        for item in payload.get("results", [])[:5]:
            media_title = item.get("title") or item.get("name") or title
            poster_path = item.get("poster_path") or ""
            result.append(Metadata(title=media_title, original_title=item.get("original_title") or item.get("original_name") or "", year=(item.get("release_date") or item.get("first_air_date") or "")[:4], overview=item.get("overview") or "", poster_url=f"https://image.tmdb.org/t/p/w780{poster_path}" if poster_path else "", source=self.name))
        return result
