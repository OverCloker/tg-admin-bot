from __future__ import annotations

import aiohttp

from .base import MetadataProvider


class OmdbProvider(MetadataProvider):
    name = "OMDb"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, title: str, season: int | None = None):
        if not self.api_key:
            return []
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.omdbapi.com/", params={"apikey": self.api_key, "t": title, "type": "series" if season else "movie"}, timeout=15) as response:
                response.raise_for_status()
                payload = await response.json()
        if payload.get("Response") != "True":
            return []
        return [self._metadata(payload)]

    def _metadata(self, payload):
        from .base import Metadata

        genres = [item.strip() for item in (payload.get("Genre") or "").split(",") if item.strip()]
        cast = [item.strip() for item in (payload.get("Actors") or "").split(",") if item.strip()]
        return Metadata(title=payload.get("Title") or "", original_title=payload.get("Title") or "", year=payload.get("Year") or "", overview=payload.get("Plot") or "", poster_url=payload.get("Poster") or "", genres=genres, cast=cast, imdb_rating=payload.get("imdbRating") or "", imdb_votes=payload.get("imdbVotes") or "", country=payload.get("Country") or "", director=payload.get("Director") or "", age_rating=payload.get("Rated") or "", source=self.name)
