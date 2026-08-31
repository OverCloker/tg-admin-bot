from __future__ import annotations

from .base import MetadataProvider


class RezkaProvider(MetadataProvider):
    """Provider boundary for Rezka; mirror discovery is intentionally isolated."""

    name = "Rezka"

    def __init__(self, domain: str = ""):
        self.domain = domain.strip().rstrip("/")

    async def search(self, title: str, season: int | None = None):
        # Rezka markup and mirrors change frequently; keep the provider seam
        # ready without coupling the MVP scanner to an unstable scraper.
        return []

