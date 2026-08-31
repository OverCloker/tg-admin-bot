from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaFileInfo:
    path: Path
    filename: str
    title: str
    season_number: int | None = None
    episode_number: int | None = None
    dub: str | None = None
    age_rating: str | None = None
    quality: str | None = None
    additional_tags: list[str] = field(default_factory=list)
    warning: str | None = None


@dataclass
class SeasonGroup:
    title: str
    season_number: int
    episodes: list[MediaFileInfo] = field(default_factory=list)
    dub: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def missing_episodes(self) -> list[int]:
        numbers = {item.episode_number for item in self.episodes if item.episode_number is not None}
        if not numbers:
            return []
        return [number for number in range(1, max(numbers) + 1) if number not in numbers]


@dataclass
class ShowGroup:
    title: str
    seasons: list[SeasonGroup] = field(default_factory=list)

