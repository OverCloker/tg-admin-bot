"""Alert provider contract and NEPTUN active-threat adapter."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import aiohttp


SOURCE_LABELS = {"alerts_in_ua": "Alerts.in.ua", "neptun": "NEPTUN"}
DEFAULT_NEPTUN_LOCATION = "kryvyi-rih"
NEPTUN_NOTICE = (
    '\n\nДанные: <a href="https://neptun.in.ua/">NEPTUN</a>. '
    "Информационный агрегатор; возможны задержки и неточности. "
    "Следуйте официальным сигналам воздушной тревоги."
)


@dataclass(frozen=True)
class AlertLocation:
    key: str
    city: str
    district: str | None
    oblast: str

    @property
    def official_area(self) -> str:
        return self.district or self.oblast


def _location(key: str, city: str, district: str | None, oblast: str) -> AlertLocation:
    return AlertLocation(key, city, district, oblast)


def _normalize_geo_name(value: str) -> str:
    return value.strip().casefold().replace("’", "'").replace("ʼ", "'").replace("`", "'")


# Cities published in NEPTUN's sitemap on 2026-09-13. The district/oblast map
# lets one shared threat snapshot be filtered independently for each group.
NEPTUN_LOCATIONS = {
    item.key: item
    for item in (
        _location("bila-tserkva", "Біла Церква", "Білоцерківський район", "Київська область"),
        _location("brovary", "Бровари", "Броварський район", "Київська область"),
        _location("cherkasy", "Черкаси", "Черкаський район", "Черкаська область"),
        _location("chernihiv", "Чернігів", "Чернігівський район", "Чернігівська область"),
        _location("chernivtsi", "Чернівці", "Чернівецький район", "Чернівецька область"),
        _location("chuhuiv", "Чугуїв", "Чугуївський район", "Харківська область"),
        _location("dnipro", "Дніпро", "Дніпровський район", "Дніпропетровська область"),
        _location("ivano-frankivsk", "Івано-Франківськ", "Івано-Франківський район", "Івано-Франківська область"),
        _location("izium", "Ізюм", "Ізюмський район", "Харківська область"),
        _location("izmail", "Ізмаїл", "Ізмаїльський район", "Одеська область"),
        _location("kamianske", "Кам’янське", "Кам’янський район", "Дніпропетровська область"),
        _location("kharkiv", "Харків", "Харківський район", "Харківська область"),
        _location("kherson", "Херсон", "Херсонський район", "Херсонська область"),
        _location("khmelnytskyi", "Хмельницький", "Хмельницький район", "Хмельницька область"),
        _location("konotop", "Конотоп", "Конотопський район", "Сумська область"),
        _location("kramatorsk", "Краматорськ", "Краматорський район", "Донецька область"),
        _location("kremenchuk", "Кременчук", "Кременчуцький район", "Полтавська область"),
        _location("kropyvnytskyi", "Кропивницький", "Кропивницький район", "Кіровоградська область"),
        _location("kupiansk", "Куп’янськ", "Куп’янський район", "Харківська область"),
        _location("kyiv-city", "Київ", None, "м. Київ"),
        _location("kryvyi-rih", "Кривий Ріг", "Криворізький район", "Дніпропетровська область"),
        _location("lozova", "Лозова", "Лозівський район", "Харківська область"),
        _location("lutsk", "Луцьк", "Луцький район", "Волинська область"),
        _location("lviv", "Львів", "Львівський район", "Львівська область"),
        _location("mykolaiv", "Миколаїв", "Миколаївський район", "Миколаївська область"),
        _location("nikopol", "Нікополь", "Нікопольський район", "Дніпропетровська область"),
        _location("odesa", "Одеса", "Одеський район", "Одеська область"),
        _location("okhtyrka", "Охтирка", "Охтирський район", "Сумська область"),
        _location("oleksandriia", "Олександрія", "Олександрійський район", "Кіровоградська область"),
        _location("pavlohrad", "Павлоград", "Павлоградський район", "Дніпропетровська область"),
        _location("poltava", "Полтава", "Полтавський район", "Полтавська область"),
        _location("rivne", "Рівне", "Рівненський район", "Рівненська область"),
        _location("shostka", "Шостка", "Шосткинський район", "Сумська область"),
        _location("sloviansk", "Слов’янськ", "Краматорський район", "Донецька область"),
        _location("sumy", "Суми", "Сумський район", "Сумська область"),
        _location("ternopil", "Тернопіль", "Тернопільський район", "Тернопільська область"),
        _location("uman", "Умань", "Уманський район", "Черкаська область"),
        _location("uzhhorod", "Ужгород", "Ужгородський район", "Закарпатська область"),
        _location("vinnytsia", "Вінниця", "Вінницький район", "Вінницька область"),
        _location("zaporizhzhia", "Запоріжжя", "Запорізький район", "Запорізька область"),
        _location("zhytomyr", "Житомир", "Житомирський район", "Житомирська область"),
    )
}


@dataclass(frozen=True)
class AlertsThreat:
    threat_type: str
    level: str | None
    started_at: str | None
    source_message: str | None
    location_title: str | None = None


@dataclass(frozen=True)
class AlertsLocationState:
    status: str
    alert_level: str | None = None
    threats: tuple[AlertsThreat, ...] = ()
    source: str = "alerts_in_ua"
    location_title: str = "Криворізький район"
    official_area: str | None = None


class AlertProvider(Protocol):
    async def fetch(self) -> object: ...

    def state_for(self, snapshot: object, location_key: str) -> AlertsLocationState: ...


@dataclass
class AlertsInUaProvider:
    """Adapter retaining the existing authenticated Alerts.in.ua fetch."""

    fetch_state: Callable[[], Awaitable[AlertsLocationState]]

    async def fetch(self) -> AlertsLocationState:
        return await self.fetch_state()

    def state_for(self, snapshot: object, location_key: str) -> AlertsLocationState:
        if not isinstance(snapshot, AlertsLocationState):
            raise ValueError("Alerts.in.ua: invalid state")
        return snapshot


def parse_neptun_alerts(
    payload: object,
    location_key: str = DEFAULT_NEPTUN_LOCATION,
) -> AlertsLocationState:
    """Convert NEPTUN active threats to a state for one configured city."""

    location = NEPTUN_LOCATIONS.get(location_key)
    if location is None:
        raise ValueError("NEPTUN: unknown location")
    if not isinstance(payload, dict):
        raise ValueError("NEPTUN: expected an alert snapshot")
    items = payload.get("threats")
    if not isinstance(items, list):
        raise ValueError("NEPTUN: missing threats list")

    normalized_city = _normalize_geo_name(location.city)
    normalized_district = _normalize_geo_name(location.district or "")
    normalized_oblast = _normalize_geo_name(location.oblast)
    type_map = {
        "uav": ("drones", "yellow"),
        "fpv": ("drones", "yellow"),
        "recon": ("drones", "yellow"),
        "missile": ("unspecified_missiles", "red"),
        "ballistic": ("ballistic_missiles", "red"),
        "kab": ("guided_aerial_bombs", "red"),
        "mig31k": ("mig31k_departure", "red"),
        "unknown": ("unknown", None),
    }
    matched: list[AlertsThreat] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("NEPTUN: invalid threat entry")
        raw_type = item.get("type")
        status = item.get("status")
        if not isinstance(raw_type, str) or not raw_type.strip() or not isinstance(status, str):
            raise ValueError("NEPTUN: invalid threat fields")
        if status.strip().casefold() != "active" or bool(item.get("advisory")):
            continue
        region = _normalize_geo_name(str(item.get("region") or ""))
        district = _normalize_geo_name(str(item.get("district") or ""))
        locality = _normalize_geo_name(str(item.get("locality") or ""))
        explanation = str(item.get("explanationShort") or "").strip()
        explanation_geo = _normalize_geo_name(explanation)
        region_matches = region == normalized_oblast or (
            location.key == "kyiv-city" and region in {"київ", "м. київ"}
        )
        direct_match = (
            locality == normalized_city and (not region or region_matches)
        ) or (normalized_city in explanation_geo and region_matches)
        district_match = bool(normalized_district and district == normalized_district)
        area_match = region_matches and (bool(item.get("areaOnly")) or location.district is None)
        if not (direct_match or (region_matches and district_match) or area_match):
            continue
        threat_type, level = type_map.get(raw_type.strip().casefold(), ("unknown", None))
        scope = str(item.get("locality") or item.get("district") or item.get("region") or "").strip()
        matched.append(
            AlertsThreat(
                threat_type=threat_type,
                level=level,
                started_at=str(item.get("confirmedAt") or item.get("updatedAt") or "").strip() or None,
                source_message=explanation or str(item.get("title") or "").strip() or None,
                location_title=scope or None,
            )
        )
    alert_level = (
        "red" if any(item.level == "red" for item in matched)
        else "yellow" if any(item.level == "yellow" for item in matched)
        else None
    )
    return AlertsLocationState(
        "A" if matched else "N",
        alert_level=alert_level,
        threats=tuple(matched),
        source="neptun",
        location_title=location.city,
        official_area=(
            f"{location.official_area}, {location.oblast}"
            if location.district
            else location.oblast
        ),
    )


class NeptunProvider:
    """Fetch one shared snapshot; derive each group's city state locally."""

    async def fetch(self) -> object:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get("https://neptun.in.ua/api/v1/threats") as response:
                response.raise_for_status()
                return await response.json()

    def state_for(self, snapshot: object, location_key: str) -> AlertsLocationState:
        return parse_neptun_alerts(snapshot, location_key)
