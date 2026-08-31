from __future__ import annotations

from pathlib import Path

from ..models import SeasonGroup
from ..telegram.base_transport import TelegramTransport


class PublicationService:
    def __init__(self, transport: TelegramTransport, chat_id: str, thread_id: str = ""):
        self.transport = transport
        self.chat_id = chat_id
        self.thread_id = thread_id

    async def publish_season(self, season: SeasonGroup, card_text: str = "") -> list[dict]:
        if card_text:
            await self.transport.send_message(card_text, self.chat_id, self.thread_id)
        results: list[dict] = []
        episodes = [item.path for item in season.episodes if item.episode_number is not None and item.path.is_file()]
        for start in range(0, len(episodes), 10):
            batch = episodes[start : start + 10]
            first = season.episodes[start].episode_number or start + 1
            last = season.episodes[start + len(batch) - 1].episode_number or first + len(batch) - 1
            caption = f"{season.season_number} сезон\nСерии {first}-{last}"
            if season.dub:
                caption += f"\nДубляж: {season.dub}"
            results.extend(await self.transport.send_media_group(batch, caption, self.chat_id, self.thread_id))
        return results

