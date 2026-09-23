import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True)
class WeatherPlace:
    latitude: float
    longitude: float
    label: str
    source: str
    score: int


WEATHER_UA_HINT_RE = re.compile(
    r"\b(укра[иї]на|украине|україні|область|обл\.?|район|р-н|крив|киев|київ|днепр|дніпр|одесс|одес|харьк|харків|льв[іо]в)\b",
    re.IGNORECASE,
)
WEATHER_ADDRESS_HINT_RE = re.compile(
    r"\b(улица|вулиця|ул\.?|проспект|просп\.?|провулок|переулок|шоссе|шосе|"
    r"бульвар|набережная|набережна|площадь|площа|дом|будинок)\b",
    re.IGNORECASE,
)
WEATHER_STOP_WORDS = {
    "село", "села", "поселок", "посёлок", "смт", "пгт", "город", "місто",
    "район", "область", "обл", "украина", "україна",
}
NOMINATIM_SETTLEMENT_TYPES = {
    "city", "town", "village", "hamlet", "municipality", "isolated_dwelling",
}


WEATHER_KRYVYI_RIH_FALLBACKS = {
    "авангард": WeatherPlace(
        48.010278,
        33.316111,
        "Авангард, Кривой Рог, Днепропетровская область, Украина",
        "local",
        1000,
    ),
    "марьяновка": WeatherPlace(
        47.999444,
        33.293333,
        "Марьяновка, Криворожский район, Днепропетровская область, Украина",
        "local",
        1000,
    ),
    "маряновка": WeatherPlace(
        47.999444,
        33.293333,
        "Марьяновка, Криворожский район, Днепропетровская область, Украина",
        "local",
        1000,
    ),
    "мар'янівка": WeatherPlace(
        47.999444,
        33.293333,
        "Мар'янівка, Криворізький район, Дніпропетровська область, Україна",
        "local",
        1000,
    ),
    "марянівка": WeatherPlace(
        47.999444,
        33.293333,
        "Мар'янівка, Криворізький район, Дніпропетровська область, Україна",
        "local",
        1000,
    ),
}


def normalize_weather_query(query: str) -> str:
    normalized = query.casefold().replace("ё", "е").replace("’", "'").replace("ʼ", "'")
    return " ".join(re.sub(r"[^\wа-яА-ЯіїєґІЇЄҐ']+", " ", normalized).split())


def weather_query_tokens(query: str) -> list[str]:
    return [
        token
        for token in normalize_weather_query(query).split()
        if len(token) > 2 and token not in WEATHER_STOP_WORDS
    ]


def local_weather_place(query: str) -> WeatherPlace | None:
    if WEATHER_ADDRESS_HINT_RE.search(query):
        return None
    tokens = set(weather_query_tokens(query))
    for name, place in WEATHER_KRYVYI_RIH_FALLBACKS.items():
        if name not in tokens:
            continue
        context = tokens - {name}
        if not context or any(
            token.startswith(("крив", "днепр", "дніпр"))
            for token in context
        ):
            return place
    return None


def weather_place_score(query: str, label: str, country_code: str | None = None) -> int:
    tokens = weather_query_tokens(query)
    normalized_label = normalize_weather_query(label)
    score = 0
    if country_code and country_code.casefold() == "ua":
        score += 30 if WEATHER_UA_HINT_RE.search(query) else 12
    for token in tokens:
        if token in normalized_label:
            score += 12
        elif token.startswith("крив") and ("крив" in normalized_label or "kryv" in normalized_label):
            score += 20
        elif token.startswith("дніпр") and (
            "дніпр" in normalized_label or "днепр" in normalized_label or "dnipr" in normalized_label
        ):
            score += 16
        else:
            score -= 2
    if tokens and normalized_label.startswith(tokens[0]):
        score += 10
    return score


def format_open_meteo_place(place: dict, fallback: str) -> str:
    parts = [str(place.get("name") or fallback)]
    for key in ("admin3", "admin2", "admin1", "country"):
        value = place.get(key)
        if value and str(value) not in parts:
            parts.append(str(value))
    return ", ".join(parts)


def open_meteo_result_is_settlement(item: object) -> bool:
    return isinstance(item, dict) and str(item.get("feature_code") or "").upper().startswith("PPL")


def nominatim_result_is_settlement(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    address_type = str(item.get("addresstype") or item.get("type") or "").casefold()
    return address_type in NOMINATIM_SETTLEMENT_TYPES


def format_nominatim_place(item: dict, fallback: str) -> str:
    address = item.get("address") if isinstance(item.get("address"), dict) else {}
    name = str(item.get("name") or "").strip()
    if not name:
        for key in NOMINATIM_SETTLEMENT_TYPES:
            if address.get(key):
                name = str(address[key]).strip()
                break
    parts = [name or fallback]
    for key in ("county", "state_district", "state", "country"):
        value = str(address.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


async def geocode_open_meteo(session: aiohttp.ClientSession, query: str) -> list[WeatherPlace]:
    url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote(query)}&count=10&language=ru&format=json"
    )
    async with session.get(url, headers={"User-Agent": "telegram-autoreply-bot"}) as response:
        if response.status != 200:
            raise RuntimeError(f"geocoding service returned {response.status}")
        data = await response.json(content_type=None)

    places: list[WeatherPlace] = []
    for item in data.get("results") or []:
        if not open_meteo_result_is_settlement(item):
            continue
        label = format_open_meteo_place(item, query)
        places.append(WeatherPlace(
            float(item["latitude"]),
            float(item["longitude"]),
            label,
            "open-meteo",
            weather_place_score(query, label, item.get("country_code")),
        ))
    return places


async def geocode_nominatim(session: aiohttp.ClientSession, query: str) -> list[WeatherPlace]:
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={quote(query)}&format=jsonv2&addressdetails=1&limit=8&accept-language=ru,uk,en"
    )
    async with session.get(url, headers={"User-Agent": "telegram-autoreply-bot/1.0"}) as response:
        if response.status != 200:
            return []
        data = await response.json(content_type=None)

    places: list[WeatherPlace] = []
    for item in data if isinstance(data, list) else []:
        if not nominatim_result_is_settlement(item):
            continue
        label = format_nominatim_place(item, query)
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        places.append(WeatherPlace(
            float(item["lat"]),
            float(item["lon"]),
            label,
            "osm",
            weather_place_score(query, label, str(address.get("country_code") or "")) + 8,
        ))
    return places


async def resolve_weather_place(session: aiohttp.ClientSession, query: str) -> WeatherPlace:
    if WEATHER_ADDRESS_HINT_RE.search(query):
        raise RuntimeError("settlement required")
    local = local_weather_place(query)
    if local is not None:
        return local

    candidates: list[WeatherPlace] = []
    provider_failed = False
    for geocode in (geocode_nominatim, geocode_open_meteo):
        try:
            candidates.extend(await geocode(session, query))
        except (aiohttp.ClientError, TimeoutError, RuntimeError):
            provider_failed = True
    if not candidates:
        raise RuntimeError("geocoding unavailable" if provider_failed else "settlement not found")
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[0]
