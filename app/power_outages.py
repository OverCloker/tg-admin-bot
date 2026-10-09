"""Read-only, cached adapter for settlements supported by Bez Svitla."""
import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix='/power', tags=['Power schedules'])
BASE = 'https://bezsvitla.com.ua'
KYIV = ZoneInfo('Europe/Kyiv')
GROUPS = tuple(f'{i}.{j}' for i in range(1, 7) for j in (1, 2))
_cache: dict[str, tuple[float, str, str]] = {}
_requests = asyncio.Semaphore(3)


class SlotParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.status = 'unknown'
        self.capture = False
        self.text = ''
        self.slots = []
        self.title = ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get('class', '').split()
        if tag == 'title':
            self.in_title = True
        if 'bz-schedule-slot' in classes:
            self.status = ('off' if 'bz-schedule-slot--off' in classes else
                           'on' if 'bz-schedule-slot--on' in classes else 'unknown')
        if 'bz-schedule-slot__time' in classes:
            self.capture, self.text = True, ''

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.capture:
            self.text += data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'span' and self.capture:
            self.capture = False
            match = re.fullmatch(r'\s*(\d{2}):(\d{2})\s*[–—-]\s*(\d{2}):(\d{2})\s*', self.text)
            if match:
                h1, m1, h2, m2 = map(int, match.groups())
                if h1 < 24 and m1 < 60 and h2 <= 24 and m2 < 60 and (h2 < 24 or m2 == 0):
                    self.slots.append({'start': h1*60+m1, 'end': h2*60+m2, 'status': self.status})


def parse_schedule(html: str, day: date) -> list[dict]:
    parser = SlotParser()
    parser.feed(html)
    # Dated pages must identify the requested day. Never pass yesterday off as today.
    if day.strftime('%d.%m.%Y') not in parser.title:
        return []
    slots = sorted(parser.slots, key=lambda s: s['start'])
    end = 0
    for slot in slots:
        if slot['start'] != end or slot['end'] <= slot['start']:
            return []
        end = slot['end']
    return slots if end == 1440 else []


async def fetch_public(path: str, params: dict | None = None, ttl: int = 300) -> tuple[str, str, bool]:
    key = path + json.dumps(params or {}, sort_keys=True)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < ttl:
        return cached[1], cached[2], False
    try:
        async with _requests, aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(BASE + path, params=params, allow_redirects=False,
                                   headers={'User-Agent': 'Mozilla/5.0 (compatible; Abstergo-Outages/0.4)'}) as response:
                if response.status == 404:
                    return '', datetime.now(KYIV).isoformat(), False
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 8_000_000:
                        raise ValueError('Response too large')
                text = body.decode('utf-8')
        fetched = datetime.now(KYIV).isoformat()
        while _cache and (len(_cache) >= 128 or sum(len(v[1]) for v in _cache.values()) + len(text) > 16_000_000):
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic(), text, fetched)
        return text, fetched, False
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError) as exc:
        logging.warning('Outage source unavailable: %s (%s, HTTP %s)', path, type(exc).__name__, getattr(exc, 'status', '-'))
        if cached:
            return cached[1], cached[2], True
        raise HTTPException(503, 'Источник графиков временно недоступен')


@router.get('/locations')
async def locations(q: str = Query(min_length=2, max_length=80)):
    raw, _, stale = await fetch_public('/search-locality', {'q': q.strip()}, ttl=3600)
    try:
        values = json.loads(raw)
        result = []
        for item in values:
            href = item.get('url', '')
            parsed = urlparse(href)
            same_origin = parsed.hostname == 'bezsvitla.com.ua' or (not parsed.netloc and not parsed.scheme and href.startswith('/'))
            if same_origin and valid_location(parsed.path):
                result.append({'name': str(item['name'])[:240], 'path': parsed.path})
        return {'locations': result[:20], 'region': 'Україна', 'groups': GROUPS, 'stale': stale}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, 'Не удалось прочитать каталог населённых пунктов')


def valid_location(path: str) -> bool:
    return (path == '/kyiv' or bool(re.fullmatch(r'/[a-z]+(?:-[a-z]+)*-oblast/(?:[a-z0-9-]+/)?[a-z0-9-]+', path))) and not any(
        part.startswith(('cherha-', 'grafik-')) for part in path.split('/'))


def queue_links(html: str, region: str) -> dict[str, str]:
    """Only queue URLs advertised by this region, never arbitrary upstream URLs."""
    result = {}
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        path = urlparse(unescape(href)).path
        match = re.fullmatch(re.escape(region) + r'/cherha-(\d{1,2})(?:-(\d{1,2}))?', path)
        if match:
            result[match[1] + ('.' + match[2] if match[2] else '')] = path
    return result


async def location_queues(location: str) -> tuple[dict[str, str], bool]:
    region = '/' + location.split('/')[1]
    html, _, stale = await fetch_public(location, ttl=900)
    queues = queue_links(html, region)
    if not queues:
        html, _, region_stale = await fetch_public(region, ttl=900)
        queues = queue_links(html, region)
        stale = stale or region_stale
    return queues, stale


@router.get('/options')
async def options(location: str):
    if not valid_location(location):
        raise HTTPException(422, 'Выберите населённый пункт из поиска')
    queues, stale = await location_queues(location)
    return {'groups': list(queues) or list(GROUPS), 'available': bool(queues), 'stale': stale}


@router.get('/schedule')
async def schedule(location: str, group: str, day: date | None = None):
    if not valid_location(location) or not re.fullmatch(r'[1-9]\d?(?:\.[1-9]\d?)?', group):
        raise HTTPException(422, 'Выберите населённый пункт из поиска и свою группу')
    today = datetime.now(KYIV).date()
    day = day or today
    if day not in (today, today + timedelta(days=1)):
        raise HTTPException(422, 'Доступны графики на сегодня и завтра')
    queues, queue_stale = await location_queues(location)
    if not queues and day > today:
        region = '/' + location.split('/')[1]
        for base in dict.fromkeys((location, region)):
            html, _, dated_stale = await fetch_public(base + f'/grafik-na-{day.isoformat()}')
            queues.update(queue_links(html, region))
            queue_stale = queue_stale or dated_stale
            if queues:
                break
    queue_path = queues.get(group)
    # Existing Poltava installations may have a manually chosen regional group.
    # Retain that choice, but always resolve within the selected region.
    if not queue_path and queues:
        region = '/' + location.split('/')[1]
        html, _, region_stale = await fetch_public(region, ttl=900)
        queue_path = queue_links(html, region).get(group)
        queue_stale = queue_stale or region_stale
    path = (queue_path or location) + f'/grafik-na-{day.isoformat()}'
    if not queue_path:
        return {'date': day.isoformat(), 'group': group, 'location': location,
                'published': False, 'intervals': [], 'fetchedAt': datetime.now(KYIV).isoformat(),
                'sourceUpdated': '', 'stale': queue_stale, 'sourceUrl': BASE + path, 'timezone': 'Europe/Kyiv'}
    html, fetched, stale = await fetch_public(path)
    stale = stale or queue_stale
    slots = parse_schedule(html, day)
    plain = unescape(re.sub(r'<[^>]+>', ' ', html))
    updated = re.search(r'Оновлено\s*(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})', plain)
    return {'date': day.isoformat(), 'group': group, 'location': location,
            'published': bool(slots), 'intervals': slots, 'fetchedAt': fetched,
            'sourceUpdated': updated.group(1) if updated else '', 'stale': stale,
            'sourceUrl': BASE + path, 'timezone': 'Europe/Kyiv'}
