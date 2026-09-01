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
    imdb_rating: str = ""
    imdb_votes: str = ""
    kinopoisk_rating: str = ""
    kinopoisk_votes: str = ""
    country: str = ""
    director: str = ""
    age_rating: str = ""
    source_url: str = ""
    source: str = ""


class MetadataProvider:
    name = "provider"

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        raise NotImplementedError


class NullMetadataProvider(MetadataProvider):
    name = "local"

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        return [Metadata(title=title, source=self.name)]
