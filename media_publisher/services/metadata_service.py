from __future__ import annotations

import json
from dataclasses import fields
from difflib import SequenceMatcher

from ..database.repository import PublisherDatabase
from ..providers.base import Metadata, MetadataProvider, NullMetadataProvider


def _score(left: Metadata, right: Metadata) -> float:
    title_score = SequenceMatcher(None, left.title.casefold(), right.title.casefold()).ratio()
    if left.year and right.year and left.year != right.year:
        title_score -= 0.25
    return title_score


def _merge(primary: Metadata, fallback: Metadata) -> Metadata:
    list_fields = {"genres", "cast", "episode_numbers", "poster_options"}
    for descriptor in fields(Metadata):
        name = descriptor.name
        if name in {"source", "source_url", "external_id", "media_type"}:
            continue
        current = getattr(primary, name)
        incoming = getattr(fallback, name)
        if name in list_fields:
            if not current and incoming:
                setattr(primary, name, list(incoming))
        elif not current and incoming:
            setattr(primary, name, incoming)
    if fallback.source and fallback.source not in primary.source.split("+"):
        primary.source = "+".join(part for part in (primary.source, fallback.source) if part)
    return primary


class MetadataService:
    def __init__(self, database: PublisherDatabase, providers: list[MetadataProvider] | None = None):
        self.database = database
        self.providers = providers or [NullMetadataProvider()]

    @staticmethod
    def lookup_key(title: str, season: int | None = None) -> str:
        return f"{title.casefold().strip()}:{season or 0}"

    async def find(self, title: str, season: int | None = None, *, force: bool = False) -> list[Metadata]:
        compact_title = "".join(char for char in title if char.isalnum())
        if len(compact_title) < 3 or compact_title.isdigit():
            return []
        lookup_key = self.lookup_key(title, season)
        if not force:
            selected = self.database.load_metadata_selection(lookup_key)
            if selected:
                return [Metadata(**json.loads(selected))]
        cache_key = f"v3:{lookup_key}"
        if not force:
            row = self.database.connection.execute("select payload from metadata_cache where cache_key=?", (cache_key,)).fetchone()
            if row:
                payload = json.loads(row["payload"])
                records = payload if isinstance(payload, list) else [payload]
                return [Metadata(**record) for record in records]

        provider_results: list[tuple[MetadataProvider, list[Metadata]]] = []
        for provider in self.providers:
            try:
                results = await provider.search(title, season)
            except Exception:
                continue
            if results:
                provider_results.append((provider, results))
        if not provider_results:
            return []

        primary_provider, primary_results = provider_results[0]
        merged_results: list[Metadata] = []
        for primary in primary_results:
            try:
                primary = await primary_provider.enrich(primary, season)
            except Exception:
                pass
            for provider, candidates in provider_results[1:]:
                candidate = max(candidates, key=lambda item: _score(primary, item))
                if _score(primary, candidate) < 0.62:
                    continue
                try:
                    candidate = await provider.enrich(candidate, season)
                except Exception:
                    pass
                primary = _merge(primary, candidate)
            primary.season_number = season
            merged_results.append(primary)

        serialised = [item.__dict__ for item in merged_results]
        self.database.connection.execute(
            "insert or replace into metadata_cache(cache_key,provider,payload,updated_at) values(?,?,?,datetime('now'))",
            (cache_key, primary_provider.name, json.dumps(serialised, ensure_ascii=False)),
        )
        self.database.connection.commit()
        return merged_results

    def save_selection(self, title: str, season: int | None, metadata: Metadata) -> None:
        self.database.save_metadata_selection(
            self.lookup_key(title, season),
            json.dumps(metadata.__dict__, ensure_ascii=False),
        )
