from __future__ import annotations

import json

from ..database.repository import PublisherDatabase
from ..providers.base import Metadata, MetadataProvider, NullMetadataProvider


class MetadataService:
    def __init__(self, database: PublisherDatabase, providers: list[MetadataProvider] | None = None):
        self.database = database
        self.providers = providers or [NullMetadataProvider()]

    async def find(self, title: str, season: int | None = None) -> list[Metadata]:
        cache_key = f"v2:{title.casefold()}:{season or 0}"
        row = self.database.connection.execute("select payload from metadata_cache where cache_key=?", (cache_key,)).fetchone()
        if row:
            payload = json.loads(row["payload"])
            records = payload if isinstance(payload, list) else [payload]
            return [Metadata(**record) for record in records]
        for provider in self.providers:
            try:
                results = await provider.search(title, season)
            except Exception:
                continue
            if results:
                serialised = [item.__dict__ for item in results]
                self.database.connection.execute("insert or replace into metadata_cache(cache_key,provider,payload,updated_at) values(?,?,?,datetime('now'))", (cache_key, provider.name, json.dumps(serialised, ensure_ascii=False)))
                self.database.connection.commit()
                return results
        return []
