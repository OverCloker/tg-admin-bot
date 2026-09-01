from __future__ import annotations

import json
import re
import asyncio
import hashlib
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from .base import Metadata, MetadataProvider


DEFAULT_MIRRORS = (
    "https://g.hdrezka.info", "https://n.hdrezka.info", "https://hdrezka.co",
    "https://hdrezka.ag", "https://rezka.ag", "https://rezka-ua.tv", "https://hdrzk.org",
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,uk;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}
ANUBIS_PASS_PATH = "/.within.website/x/cmd/anubis/api/pass-challenge"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalise_title(value: str) -> str:
    value = re.sub(r"\([^)]*(?:19|20)\d{2}[^)]*\)", "", value.casefold())
    value = re.split(r"\b(?:смотреть|дивитися|онлайн|online)\b", value, maxsplit=1)[0]
    return " ".join(re.findall(r"[a-zа-яёіїєґ0-9]+", value, re.I))


def _is_relevant(query: str, candidate: str) -> bool:
    expected = _normalise_title(query)
    actual = _normalise_title(candidate)
    if not expected or not actual or len(expected.replace(" ", "")) < 3 or expected.replace(" ", "").isdigit():
        return False
    if expected in actual or actual in expected:
        return True
    return SequenceMatcher(None, expected, actual).ratio() >= 0.62


def _solve_anubis_pow(random_data: str, difficulty: int) -> tuple[str, int]:
    if not random_data or difficulty < 1 or difficulty > 7:
        raise RuntimeError("Некорректные параметры антибот-проверки Rezka.")
    prefix = "0" * difficulty
    for nonce in range(1 << 30):
        digest = hashlib.sha256(f"{random_data}{nonce}".encode()).hexdigest()
        if digest.startswith(prefix):
            return digest, nonce
    raise RuntimeError("Не удалось пройти антибот-проверку Rezka.")


class RezkaProvider(MetadataProvider):
    name = "Rezka"

    def __init__(self, domain: str = "", mirrors_path: str | Path | None = None, timeout: int = 20):
        self.domain = self._normalise_domain(domain)
        self.mirrors_path = Path(mirrors_path) if mirrors_path else Path(__file__).parents[1] / "config" / "rezka_mirrors.json"
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.active_domain = ""

    @staticmethod
    def _normalise_domain(domain: str) -> str:
        value = domain.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            value = "https://" + value
        return value

    def _mirrors(self) -> list[str]:
        configured: list[str] = []
        if self.mirrors_path.is_file():
            try:
                payload = json.loads(self.mirrors_path.read_text(encoding="utf-8"))
                configured = payload.get("mirrors", []) if isinstance(payload, dict) else payload
            except (OSError, json.JSONDecodeError):
                configured = []
        result: list[str] = []
        for value in (self.domain, *configured, *DEFAULT_MIRRORS):
            normalised = self._normalise_domain(str(value))
            if normalised and normalised not in result:
                result.append(normalised)
        return result

    @staticmethod
    def _looks_like_rezka(html: str) -> bool:
        lowered = html.casefold()
        has_markup = any(marker in lowered for marker in ("b-content__inline", "b-topnav", "b-post__title", "b-search__live_section"))
        return has_markup and "cloudflare" not in lowered and "anubis_challenge" not in lowered

    async def _get(self, session: aiohttp.ClientSession, url: str, params: dict | None = None) -> str:
        async with session.get(url, params=params, headers=HEADERS, allow_redirects=True) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            html = await response.text(errors="replace")
            final_url = str(response.url)
        if "anubis_challenge" in html:
            await self._solve_anubis(session, html, final_url)
            async with session.get(url, params=params, headers=HEADERS, allow_redirects=True) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                html = await response.text(errors="replace")
        return html

    async def _solve_anubis(self, session: aiohttp.ClientSession, html: str, page_url: str) -> None:
        soup = BeautifulSoup(html, "html.parser")
        challenge_node = soup.select_one("#anubis_challenge")
        if not challenge_node:
            raise RuntimeError("Rezka вернула неизвестную антибот-проверку.")
        try:
            challenge = json.loads(challenge_node.get_text(strip=True))
            difficulty = int(challenge["rules"]["difficulty"])
            challenge_id = str(challenge["challenge"]["id"])
            random_data = str(challenge["challenge"]["randomData"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Не удалось прочитать антибот-проверку Rezka.") from exc
        base_prefix = ""
        prefix_node = soup.select_one("#anubis_base_prefix")
        if prefix_node:
            try:
                base_prefix = str(json.loads(prefix_node.get_text(strip=True)))
            except json.JSONDecodeError:
                base_prefix = ""
        started = time.monotonic()
        digest, nonce = await asyncio.to_thread(_solve_anubis_pow, random_data, difficulty)
        from urllib.parse import urlsplit

        parsed = urlsplit(page_url)
        pass_url = f"{parsed.scheme}://{parsed.netloc}{base_prefix}{ANUBIS_PASS_PATH}"
        params = {
            "id": challenge_id,
            "response": digest,
            "nonce": str(nonce),
            "redir": page_url,
            "elapsedTime": str(int((time.monotonic() - started) * 1000) + 500),
        }
        async with session.get(pass_url, params=params, headers=HEADERS, allow_redirects=True) as response:
            if response.status >= 400:
                raise RuntimeError(f"Rezka отклонила антибот-проверку: HTTP {response.status}")

    async def search(self, title: str, season: int | None = None) -> list[Metadata]:
        query = _clean(title)
        if not query:
            return []
        connector = aiohttp.TCPConnector(ssl=False)
        cookies = {"allowed_comments": "1", "_ym_isad": "1", "_ym_visorc": "b", "dle_newpm": "0"}
        async with aiohttp.ClientSession(timeout=self.timeout, connector=connector, cookies=cookies) as session:
            for domain in self._mirrors():
                try:
                    try:
                        html = await self._get(session, f"{domain}/engine/ajax/search.php", {"q": query})
                    except (aiohttp.ClientError, TimeoutError, RuntimeError):
                        html = ""
                    links = self._parse_search_links(html, domain, query) if self._looks_like_rezka(html) else []
                    if not links:
                        html = await self._get(session, f"{domain}/search/", {"do": "search", "subaction": "search", "q": query})
                    if not self._looks_like_rezka(html):
                        continue
                    if not links:
                        links = self._parse_search_links(html, domain, query)
                    results: list[Metadata] = []
                    for link in links[:5]:
                        try:
                            detail_html = await self._get(session, link)
                            metadata = self.parse_detail_html(detail_html, link)
                            if metadata.title and _is_relevant(query, metadata.title):
                                results.append(metadata)
                        except (aiohttp.ClientError, TimeoutError, RuntimeError):
                            continue
                    if results:
                        self.active_domain = domain
                        return results
                except (aiohttp.ClientError, TimeoutError, RuntimeError):
                    continue
        return []

    @staticmethod
    def _parse_search_links(html: str, domain: str, query: str = "") -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        for item in soup.select(".b-content__inline_item"):
            anchor = item.select_one(".b-content__inline_item-link a[href]") or item.select_one("a[href]")
            if anchor and (not query or _is_relevant(query, anchor.get_text(" ", strip=True))):
                url = urljoin(domain + "/", anchor.get("href", ""))
                if url and url not in links:
                    links.append(url)
        if not links:
            for anchor in soup.select(".b-search__live_section a[href]"):
                if query and not _is_relevant(query, anchor.get_text(" ", strip=True)):
                    continue
                url = urljoin(domain + "/", anchor.get("href", ""))
                if url and url not in links:
                    links.append(url)
        return links

    @classmethod
    def parse_detail_html(cls, html: str, page_url: str) -> Metadata:
        soup = BeautifulSoup(html, "html.parser")
        title_node = soup.select_one(".b-post__title h1") or soup.select_one("h1")
        original_node = soup.select_one(".b-post__origtitle")
        poster_node = soup.select_one(".b-sidecover img[src]") or soup.select_one(".b-post__infotable img[src]")
        overview_node = soup.select_one(".b-post__description_text") or soup.select_one(".b-post__description")
        info: dict[str, str] = {}
        for row in soup.select(".b-post__info tr"):
            cells = row.select("td")
            if len(cells) >= 2:
                key = _clean(cells[0].get_text(" ", strip=True)).rstrip(":").casefold()
                if key:
                    info[key] = _clean(cells[-1].get_text(" ", strip=True))

        def info_value(*needles: str) -> str:
            for key, value in info.items():
                if any(needle in key for needle in needles):
                    return value
            return ""

        year_match = re.search(r"(?:19|20)\d{2}", info_value("год", "рік", "дата выхода", "дата виходу"))
        genres_raw = info_value("жанр")
        cast_raw = info_value("актер", "актёр", "в ролях", "у ролях", "актори")
        rating_nodes = soup.select(".b-post__rating, .b-post__rating_table, .b-post__rating_table_wrap")
        rating_text = _clean(" ".join(node.get_text(" ", strip=True) for node in rating_nodes))
        if not rating_text:
            rating_text = _clean(soup.get_text(" ", strip=True))
        imdb = re.search(r"IMDb\s*[:–-]?\s*([0-9.]+)(?:\s*\(([^)]+)\))?", rating_text, re.I)
        kinopoisk = re.search(r"КиноПоиск\s*[:–-]?\s*([0-9.]+)(?:\s*\(([^)]+)\))?", rating_text, re.I)
        poster_url = urljoin(page_url, poster_node.get("src", "")) if poster_node else ""
        return Metadata(
            title=_clean(title_node.get_text(" ", strip=True)) if title_node else "",
            original_title=_clean(original_node.get_text(" ", strip=True)) if original_node else "",
            year=year_match.group(0) if year_match else "",
            overview=_clean(overview_node.get_text(" ", strip=True)) if overview_node else "",
            poster_url=poster_url,
            genres=[part.strip() for part in re.split(r"[,/]", genres_raw) if part.strip()],
            cast=[part.strip() for part in cast_raw.split(",") if part.strip()],
            imdb_rating=imdb.group(1) if imdb else "",
            imdb_votes=imdb.group(2) if imdb and imdb.group(2) else "",
            kinopoisk_rating=kinopoisk.group(1) if kinopoisk else "",
            kinopoisk_votes=kinopoisk.group(2) if kinopoisk and kinopoisk.group(2) else "",
            country=info_value("страна", "країна"),
            director=info_value("режиссер", "режиссёр", "режисер"),
            age_rating=info_value("возраст", "вік"),
            source_url=page_url,
            source="Rezka",
        )
