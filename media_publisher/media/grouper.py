from __future__ import annotations

from collections import defaultdict

from ..models import MediaFileInfo, SeasonGroup, ShowGroup


def group_media(files: list[MediaFileInfo]) -> list[ShowGroup]:
    grouped: dict[str, dict[int, list[MediaFileInfo]]] = defaultdict(lambda: defaultdict(list))
    movies: dict[str, list[MediaFileInfo]] = defaultdict(list)
    for item in files:
        if item.media_type == "movie":
            movies[item.title].append(item)
        else:
            grouped[item.title][item.season_number or 0].append(item)
    shows: list[ShowGroup] = []
    for title in sorted(set(grouped) | set(movies), key=str.casefold):
        seasons = grouped.get(title, {})
        season_groups: list[SeasonGroup] = []
        for season_number, episodes in sorted(seasons.items()):
            episodes.sort(key=lambda item: (item.episode_number is None, item.episode_number or 0, item.filename.casefold()))
            dubs = {item.dub for item in episodes if item.dub}
            warnings = [item.warning for item in episodes if item.warning]
            if len(dubs) > 1:
                warnings.append("В сезоне обнаружена разная озвучка.")
            group = SeasonGroup(title=title, season_number=season_number, episodes=episodes, dub=next(iter(dubs), None), warnings=warnings)
            missing = group.missing_episodes
            if missing:
                warnings.append("Отсутствуют серии: " + ", ".join(map(str, missing)))
            season_groups.append(group)
        movie_files = sorted(movies.get(title, []), key=lambda item: item.filename.casefold())
        shows.append(ShowGroup(title=title, seasons=season_groups, movies=movie_files))
    return sorted(shows, key=lambda item: item.title.casefold())
