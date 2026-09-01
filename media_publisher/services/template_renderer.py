from __future__ import annotations

import re
from pathlib import Path

from ..models import SeasonGroup
from ..providers.base import Metadata


class TemplateRenderer:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else Path(__file__).parents[2] / "templates"

    def _render(self, name: str, values: dict[str, object]) -> str:
        rendered = (self.directory / name).read_text(encoding="utf-8")
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value or ""))
        rendered = re.sub(r"^.*\{[a-z_]+\}.*$", "", rendered, flags=re.M)
        if not values.get("ratings"):
            rendered = re.sub(r"(?m)^Рейтинги:\s*$", "", rendered)
        rendered = re.sub(r"(?m)^(?:Жанр|В ролях|Дубляж|Озвучка):\s*$", "", rendered)
        rendered = re.sub(r"(?:\n\s*────────────\s*){2,}", "\n────────────\n", rendered)
        rendered = re.sub(r"^(?:\s*────────────\s*)+|(?:\s*────────────\s*)+$", "", rendered)
        return re.sub(r"\n{3,}", "\n\n", rendered).strip()[:1024]

    @staticmethod
    def _ratings(metadata: Metadata) -> str:
        ratings = []
        if metadata.imdb_rating:
            ratings.append(f"IMDb: {metadata.imdb_rating}" + (f" ({metadata.imdb_votes})" if metadata.imdb_votes else ""))
        if metadata.kinopoisk_rating:
            ratings.append(f"Кинопоиск: {metadata.kinopoisk_rating}" + (f" ({metadata.kinopoisk_votes})" if metadata.kinopoisk_votes else ""))
        return "\n".join(ratings)

    def movie(self, metadata: Metadata, dub: str = "") -> str:
        original = metadata.original_title if metadata.original_title.casefold() != metadata.title.casefold() else ""
        return self._render("movie.txt", {"title": metadata.title, "original_title": original, "year": metadata.year, "ratings": self._ratings(metadata), "rankings": "\n".join(metadata.rankings), "genres": ", ".join(metadata.genres), "actors": ", ".join(metadata.cast[:12]) + (" и другие" if len(metadata.cast) > 12 else ""), "dub": dub or metadata.dub, "description": metadata.overview})

    def season(self, metadata: Metadata, season: SeasonGroup) -> str:
        title = metadata.title or season.title
        original = metadata.original_title if metadata.original_title.casefold() != title.casefold() else ""
        return self._render("season.txt", {"title": title, "original_title": original, "season_number": season.season_number, "year": metadata.season_year or metadata.year, "ratings": self._ratings(metadata), "rankings": "\n".join(metadata.rankings), "genres": ", ".join(metadata.genres), "actors": ", ".join(metadata.cast[:12]) + (" и другие" if len(metadata.cast) > 12 else ""), "dub": metadata.dub or season.dub, "description": metadata.season_overview or metadata.overview})

    def media_group(self, season: SeasonGroup, first: int, last: int) -> str:
        return self._render("media_group.txt", {"season_number": season.season_number, "episode_from": first, "episode_to": last, "dub": season.dub})
