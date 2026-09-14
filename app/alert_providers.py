"""Alert provider contract and combined NEPTUN alert adapter."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import aiohttp


SOURCE_LABELS = {
    "alerts_in_ua": "Alerts.in.ua",
    "neptun": "NEPTUN",
    "ukraine_alarm": "UkraineAlarm",
}
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
    provider_mode: str | None = None
    official_alert: bool | None = None


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
        provider_mode="threats",
    )


def parse_neptun_official_alerts(
    payload: object,
    location_key: str = DEFAULT_NEPTUN_LOCATION,
) -> AlertsLocationState:
    """Convert NEPTUN's official district/oblast alarm snapshot."""

    location = NEPTUN_LOCATIONS.get(location_key)
    if location is None:
        raise ValueError("NEPTUN: unknown location")
    if not isinstance(payload, dict):
        raise ValueError("NEPTUN: expected an alert snapshot")
    raions = payload.get("raions")
    oblasts = payload.get("oblasts")
    if not isinstance(raions, list) or not isinstance(oblasts, list):
        raise ValueError("NEPTUN: missing raions/oblasts lists")

    def find(items: list[object], expected: str, oblast: str | None = None) -> dict | None:
        normalized_expected = _normalize_geo_name(expected)
        normalized_oblast = _normalize_geo_name(oblast or "")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("NEPTUN: invalid official alert entry")
            name = item.get("name") or item.get("title")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("NEPTUN: invalid official alert entry")
            item_oblast = _normalize_geo_name(str(item.get("oblast") or ""))
            if (
                _normalize_geo_name(name) == normalized_expected
                and (not normalized_oblast or item_oblast == normalized_oblast)
            ):
                return item
        return None

    matched = find(raions, location.district, location.oblast) if location.district else None
    if matched is None:
        matched = find(oblasts, location.oblast)
    if matched is None:
        return AlertsLocationState(
            "N", source="neptun", location_title=location.city,
            official_area=location.official_area, provider_mode="alerts",
        )

    raw_level = str(matched.get("level") or "").strip().casefold()
    level = raw_level if raw_level in {"yellow", "red"} else None
    return AlertsLocationState(
        "A",
        alert_level=level,
        source="neptun",
        location_title=location.city,
        official_area=location.official_area,
        provider_mode="alerts",
    )


class NeptunProvider:
    """Combine official alarms and active threats into one city state."""

    async def fetch(self) -> object:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async def get(endpoint: str) -> object:
                async with session.get(f"https://neptun.in.ua/api/v1/{endpoint}") as response:
                    response.raise_for_status()
                    return await response.json()

            alerts, threats = await asyncio.gather(get("alerts"), get("threats"))
            return {"alerts": alerts, "threats": threats}

    def state_for(self, snapshot: object, location_key: str) -> AlertsLocationState:
        if not isinstance(snapshot, dict) or "alerts" not in snapshot or "threats" not in snapshot:
            raise ValueError("NEPTUN: incomplete combined snapshot")
        official = parse_neptun_official_alerts(snapshot["alerts"], location_key)
        details = parse_neptun_alerts(snapshot["threats"], location_key)
        official_active = official.status in {"A", "P"}
        threats_active = details.status in {"A", "P"}
        level = (
            "red" if "red" in {official.alert_level, details.alert_level}
            else "yellow" if "yellow" in {official.alert_level, details.alert_level}
            else None
        )
        return AlertsLocationState(
            official.status if official_active else (details.status if threats_active else "N"),
            alert_level=level,
            threats=details.threats,
            source="neptun",
            location_title=official.location_title,
            official_area=official.official_area,
            provider_mode="combined",
            official_alert=official_active,
        )


def _ukraine_alarm_threat_type(alert_type: str, reason: str, level: str | None) -> str:
    normalized = reason.casefold()
    if alert_type == "ARTILLERY":
        return "artillery"
    if alert_type == "URBAN_FIGHTS":
        return "urban_fights"
    if alert_type == "CHEMICAL":
        return "chemical"
    if alert_type == "NUCLEAR":
        return "nuclear"
    if alert_type == "INFO":
        return "info"
    if any(word in normalized for word in ("дрон", "бпла", "шахед")):
        return "drones"
    if "баліст" in normalized or "баллист" in normalized:
        return "ballistic_missiles"
    if "крилат" in normalized or "крылат" in normalized:
        return "cruise_missiles"
    if any(word in normalized for word in ("каб", "керован", "управляем")):
        return "guided_aerial_bombs"
    if "міг-31" in normalized or "миг-31" in normalized:
        return "mig31k_departure"
    if "ракет" in normalized:
        return "unspecified_missiles"
    if level == "yellow":
        return "air_yellow_level"
    if level == "red":
        return "air_red_level"
    return "unknown"


def parse_ukraine_alarm_alerts(
    payload: object,
    location_key: str = DEFAULT_NEPTUN_LOCATION,
) -> AlertsLocationState:
    """Convert UkraineAlarm v3 active regions and AIR levels for one city."""

    location = NEPTUN_LOCATIONS.get(location_key)
    if location is None:
        raise ValueError("UkraineAlarm: unknown location")
    if not isinstance(payload, list):
        raise ValueError("UkraineAlarm: expected a region list")
    names = {
        _normalize_geo_name(value)
        for value in (location.city, location.district or "", location.oblast)
        if value
    }
    active = False
    air_active = False
    threats: list[AlertsThreat] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for region in payload:
        if not isinstance(region, dict):
            raise ValueError("UkraineAlarm: invalid region entry")
        region_name = region.get("regionName")
        active_alerts = region.get("activeAlerts")
        if not isinstance(region_name, str) or not isinstance(active_alerts, list):
            raise ValueError("UkraineAlarm: invalid region fields")
        if _normalize_geo_name(region_name) not in names:
            continue
        for alert in active_alerts:
            if not isinstance(alert, dict) or not isinstance(alert.get("type"), str):
                raise ValueError("UkraineAlarm: invalid alert entry")
            alert_type = alert["type"].strip().upper()
            active = True
            if alert_type == "AIR":
                air_active = True
                levels = alert.get("activeAlertLevels") or []
                if not isinstance(levels, list):
                    raise ValueError("UkraineAlarm: invalid AIR levels")
                for item in levels:
                    if not isinstance(item, dict):
                        raise ValueError("UkraineAlarm: invalid AIR level")
                    raw_level = str(item.get("alertLevel") or "").strip().casefold()
                    if raw_level not in {"red", "yellow"}:
                        continue
                    reason = str(item.get("reason") or "").strip() or None
                    created_at = str(item.get("createdAt") or "").strip() or None
                    threat_type = _ukraine_alarm_threat_type(alert_type, reason or "", raw_level)
                    key = (threat_type, raw_level, reason, region_name)
                    if key not in seen:
                        seen.add(key)
                        threats.append(AlertsThreat(threat_type, raw_level, created_at, reason, region_name))
                continue
            reason = alert_type.replace("_", " ").lower()
            threat_type = _ukraine_alarm_threat_type(alert_type, reason, "red")
            key = (threat_type, "red", None, region_name)
            if key not in seen:
                seen.add(key)
                threats.append(AlertsThreat(
                    threat_type, "red", str(alert.get("lastUpdate") or "").strip() or None,
                    None, region_name,
                ))
    level = (
        "red" if any(item.level == "red" for item in threats)
        else "yellow" if any(item.level == "yellow" for item in threats)
        else None
    )
    return AlertsLocationState(
        "A" if active else "N",
        alert_level=level,
        threats=tuple(threats),
        source="ukraine_alarm",
        location_title=location.city,
        official_area=(
            f"{location.official_area}, {location.oblast}"
            if location.district else location.oblast
        ),
        provider_mode="ukraine_alarm",
        official_alert=air_active,
    )


class UkraineAlarmProvider:
    """Poll the lightweight revision and refresh all active regions on change."""

    def __init__(self, token: str) -> None:
        if not token.strip():
            raise ValueError("UkraineAlarm token is required")
        self._token = token.strip()
        self._last_action_index: int | float | None = None
        self._snapshot: object | None = None

    async def fetch(self) -> object:
        headers = {"Authorization": self._token, "Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get("https://api.ukrainealarm.com/api/v3/alerts/status") as response:
                response.raise_for_status()
                status = await response.json()
            if not isinstance(status, dict) or not isinstance(status.get("lastActionIndex"), (int, float)):
                raise ValueError("UkraineAlarm: invalid status response")
            action_index = status["lastActionIndex"]
            if self._snapshot is not None and action_index == self._last_action_index:
                return self._snapshot
            async with session.get("https://api.ukrainealarm.com/api/v3/alerts") as response:
                response.raise_for_status()
                snapshot = await response.json()
        if not isinstance(snapshot, list):
            raise ValueError("UkraineAlarm: invalid alerts response")
        self._last_action_index = action_index
        self._snapshot = snapshot
        return snapshot

    def state_for(self, snapshot: object, location_key: str) -> AlertsLocationState:
        return parse_ukraine_alarm_alerts(snapshot, location_key)
