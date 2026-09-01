from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Metadata:
    title: str
    original_title: str = ""
    year: str = ""
    overview: str = ""
    poster_url: str = ""
    genres: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    rankings: list[str] = field(default_factory=list)
    imdb_rating: str = ""
    imdb_votes: str = ""
    kinopoisk_rating: str = ""
    kinopoisk_votes: str = ""
    country: str = ""
    director: str = ""
    age_rating: str = ""
    source_url: str = ""
    external_id: str = ""
    media_type: str = ""
    season_number: int | None = None
    season_year: str = ""
    season_air_date: str = ""
    season_overview: str = ""
    season_poster_url: str = ""
    poster_path: str = ""
    poster_options: list[str] = field(default_factory=list)
    dub: str = ""
    episode_numbers: list[int] = field(default_factory=list)
    source: str = ""


class MetadataProvider:
    name = "provider"

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        raise NotImplementedError

    async def enrich(self, metadata: Metadata, season: int | None = None) -> Metadata:
        return metadata


class NullMetadataProvider(MetadataProvider):
    name = "local"

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        return [Metadata(title=title, source=self.name)]
