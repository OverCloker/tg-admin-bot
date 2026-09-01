from __future__ import annotations

from pathlib import Path

from ..models import MediaFileInfo, SeasonGroup, ShowGroup
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
        episodes = [item for item in season.episodes if item.path.is_file()]
        for start in range(0, len(episodes), 10):
            batch_items = episodes[start : start + 10]
            batch = [item.path for item in batch_items]
            first = batch_items[0].episode_number or start + 1
            last = batch_items[-1].episode_number or first + len(batch) - 1
            caption = f"{season.season_number} сезон\nСерии {first}-{last}"
            if season.dub:
                caption += f"\nДубляж: {season.dub}"
            if len(batch) >= 2 and all(path.suffix.lower() in {".mp4", ".mov", ".m4v"} for path in batch):
                results.extend(await self.transport.send_media_group(batch, caption, self.chat_id, self.thread_id))
            else:
                for index, item in enumerate(batch_items):
                    item_caption = caption if index == 0 else f"{season.title} · серия {item.episode_number or '—'}"
                    results.extend(await self.publish_media(item, item_caption))
        return results

    async def publish_media(self, media: MediaFileInfo, caption: str = "") -> list[dict]:
        if not caption:
            caption = media.title
            if media.media_type == "series" and media.episode_number:
                caption = f"{media.title} · серия {media.episode_number}"
        if media.path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            result = await self.transport.send_video(media.path, caption, self.chat_id, self.thread_id)
        else:
            result = await self.transport.send_document(media.path, caption, self.chat_id, self.thread_id)
        return [result]

    async def publish_show(self, show: ShowGroup) -> list[dict]:
        results: list[dict] = []
        for movie in show.movies:
            results.extend(await self.publish_media(movie))
        for season in show.seasons:
            results.extend(await self.publish_season(season))
        return results
