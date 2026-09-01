from __future__ import annotations

import aiohttp

from .base import Metadata, MetadataProvider


class TmdbProvider(MetadataProvider):
    name = "TMDB"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _get(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self.api_key, "language": "ru-RU", **(params or {})}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.themoviedb.org/3{path}", params=query, timeout=20) as response:
                response.raise_for_status()
                return await response.json()

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        if not self.api_key:
            return []
        payload = await self._get("/search/tv" if season else "/search/multi", {"query": title})
        result: list[Metadata] = []
        for item in payload.get("results", [])[:5]:
            media_type = item.get("media_type") or ("tv" if season else "movie")
            if media_type not in {"movie", "tv"}:
                continue
            media_title = item.get("title") or item.get("name") or title
            poster_path = item.get("poster_path") or ""
            result.append(Metadata(
                title=media_title,
                original_title=item.get("original_title") or item.get("original_name") or "",
                year=(item.get("release_date") or item.get("first_air_date") or "")[:4],
                overview=item.get("overview") or "",
                poster_url=f"https://image.tmdb.org/t/p/w780{poster_path}" if poster_path else "",
                external_id=str(item.get("id") or ""),
                media_type=media_type,
                source=self.name,
            ))
        return result

    async def enrich(self, metadata: Metadata, season: int | None = None) -> Metadata:
        if not self.api_key or not metadata.external_id:
            return metadata
        media_type = metadata.media_type or ("tv" if season else "movie")
        details = await self._get(
            f"/{media_type}/{metadata.external_id}",
            {"append_to_response": "credits,external_ids,images", "include_image_language": "ru,en,null"},
        )
        poster_path = details.get("poster_path") or ""
        metadata.genres = [item.get("name", "") for item in details.get("genres", []) if item.get("name")]
        metadata.cast = [item.get("name", "") for item in details.get("credits", {}).get("cast", [])[:15] if item.get("name")]
        metadata.overview = details.get("overview") or metadata.overview
        metadata.poster_url = f"https://image.tmdb.org/t/p/w780{poster_path}" if poster_path else metadata.poster_url
        metadata.poster_options = [
            f"https://image.tmdb.org/t/p/w780{item['file_path']}"
            for item in details.get("images", {}).get("posters", [])[:8]
            if item.get("file_path")
        ]
        metadata.country = ", ".join(item.get("name", "") for item in details.get("production_countries", []) if item.get("name"))
        if season and media_type == "tv":
            season_data = await self._get(f"/tv/{metadata.external_id}/season/{season}", {"append_to_response": "credits"})
            season_poster = season_data.get("poster_path") or ""
            metadata.season_number = season
            metadata.season_air_date = season_data.get("air_date") or ""
            metadata.season_year = metadata.season_air_date[:4]
            metadata.season_overview = season_data.get("overview") or metadata.overview
            metadata.season_poster_url = f"https://image.tmdb.org/t/p/w780{season_poster}" if season_poster else metadata.poster_url
            season_cast = [item.get("name", "") for item in season_data.get("credits", {}).get("cast", [])[:15] if item.get("name")]
            if season_cast:
                metadata.cast = season_cast
        return metadata
