"""Render a compact current air-alert map from NEPTUN's public map API."""

from __future__ import annotations

import asyncio
import io
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from .alert_providers import NEPTUN_LOCATIONS


NEPTUN_BASE_URL = "https://neptun.in.ua"
MAP_CACHE_SECONDS = 30
GEOMETRY_CACHE_SECONDS = 24 * 60 * 60
MAX_RESPONSE_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class AlertMapResult:
    image: bytes
    updated_at: datetime
    alert_count: int
    threat_count: int
    region_title: str = ""


_map_cache: tuple[float, AlertMapResult] | None = None
_geometry_cache: tuple[float, dict[str, Any], dict[str, Any]] | None = None
_cache_lock = asyncio.Lock()
_snapshot_cache: tuple[float, Any, Any] | None = None
_regional_cache: dict[str, tuple[float, AlertMapResult]] = {}


class UnknownMapRegion(ValueError):
    pass


def _geo_name(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").replace("і", "и")
                    .replace("ї", "и").replace("є", "е").replace("область", "")
                    .replace("обл.", "").split())


def resolve_map_region(query: str, oblasts: object) -> dict[str, Any]:
    name = _geo_name(query)
    aliases = {
        "днепр": "Дніпропетровська", "днипро": "Дніпропетровська",
        "днепропетровск": "Дніпропетровська", "кривой рог": "Дніпропетровська",
        "киев": "Київська", "киив": "Київська", "харьков": "Харківська",
        "одесса": "Одеська", "львов": "Львівська", "запорожье": "Запорізька",
        "николаев": "Миколаївська", "ровно": "Рівненська", "луцк": "Волинська",
        "ужгород": "Закарпатська", "ивано-франковск": "Івано-Франківська",
        "винница": "Вінницька", "житомир": "Житомирська", "сумы": "Сумська",
        "чернигов": "Чернігівська", "черкассы": "Черкаська", "черновцы": "Чернівецька",
        "донецк": "Донецька", "луганск": "Луганська", "тернополь": "Тернопільська",
        "хмельницкий": "Хмельницька", "кропивницкий": "Кіровоградська",
        "крым": "Автономна Республіка Крим",
    }
    for location in NEPTUN_LOCATIONS.values():
        if name in {_geo_name(location.city), _geo_name(location.key)}:
            name = _geo_name(location.oblast)
            break
    name = _geo_name(aliases.get(_geo_name(query), name))
    # Accept Russian oblast adjectives as well as Ukrainian names.
    name = name.replace("ская", "ська")
    matches = []
    for feature in _features(oblasts):
        props = feature.get("properties", {})
        candidates = {_geo_name(str(props.get(k) or "")) for k in ("key", "region", "name")}
        if name and name in candidates:
            return feature
        if len(name) >= 4 and any(candidate.startswith(name) for candidate in candidates):
            matches.append(feature)
    if len(matches) == 1:
        return matches[0]
    raise UnknownMapRegion("Область не найдена. Например: карта тревог днепр, карта тревог харьков или карта тревог Львівська область.")


def _inside(lon: float, lat: float, feature: dict[str, Any]) -> bool:
    for ring in _polygons(feature):
        points = _valid_points(ring)
        if not points:
            continue
        inside = False
        previous = points[-1]
        for current in points:
            x1, y1 = previous
            x2, y2 = current
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
            previous = current
        if inside:
            return True
    return False


def _belongs_to(feature: dict[str, Any], oblast: dict[str, Any]) -> bool:
    points = [point for ring in _polygons(feature) for point in _valid_points(ring)]
    if not points:
        return False
    # Centroid of the vertices stays away from shared administrative borders.
    return _inside(sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points), oblast)


def regional_payloads(raions: object, oblasts: object, alerts: object, threats: object, query: str):
    region = resolve_map_region(query, oblasts)
    selected = [f for f in _features(raions) if _belongs_to(f, region)]
    keys = {_feature_key(f) for f in selected}
    region_key = _feature_key(region)
    _alert_keys(alerts, "raions")
    _alert_keys(alerts, "oblasts")
    filtered_alerts = {
        "raions": [a for a in alerts["raions"] if isinstance(a, dict) and str(a.get("key", "")).casefold() in keys],
        "oblasts": [a for a in alerts["oblasts"] if isinstance(a, dict) and str(a.get("key", "")).casefold() == region_key],
    }
    selected_threats = []
    for threat in _active_threats(threats):
        try:
            if _inside(float(threat.get("lon")), float(threat.get("lat")), region):
                selected_threats.append(threat)
        except (TypeError, ValueError):
            continue
    return ({"type": "FeatureCollection", "features": selected},
            {"type": "FeatureCollection", "features": [region]}, filtered_alerts,
            {"threats": selected_threats}, str(region["properties"].get("region") or region["properties"].get("name") or region_key))


async def _fetch_json(session: aiohttp.ClientSession, path: str) -> Any:
    async with session.get(f"{NEPTUN_BASE_URL}{path}") as response:
        response.raise_for_status()
        if response.content_length and response.content_length > MAX_RESPONSE_BYTES:
            raise ValueError(f"NEPTUN response is too large: {path}")
        body = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError(f"NEPTUN response is too large: {path}")
            body.extend(chunk)
        return json.loads(body)


async def fetch_alert_map(region: str = "") -> AlertMapResult:
    """Return a current PNG, coalescing simultaneous calls and caching for 30 seconds."""
    global _map_cache, _geometry_cache, _snapshot_cache
    now = time.monotonic()
    if not region and _map_cache and now - _map_cache[0] < MAP_CACHE_SECONDS:
        return _map_cache[1]

    async with _cache_lock:
        now = time.monotonic()
        if not region and _map_cache and now - _map_cache[0] < MAP_CACHE_SECONDS:
            return _map_cache[1]
        region_key = ""
        if region and _geometry_cache:
            region_key = _feature_key(resolve_map_region(region, _geometry_cache[2]))
            cached = _regional_cache.get(region_key)
            if cached and now - cached[0] < MAP_CACHE_SECONDS:
                return cached[1]
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"Accept": "application/json, application/geo+json"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            geometry_fresh = bool(
                _geometry_cache and now - _geometry_cache[0] < GEOMETRY_CACHE_SECONDS
            )
            if geometry_fresh:
                raions, oblasts = _geometry_cache[1], _geometry_cache[2]
                if _snapshot_cache and now - _snapshot_cache[0] < MAP_CACHE_SECONDS:
                    alerts, threats = _snapshot_cache[1:]
                else:
                    alerts, threats = await asyncio.gather(
                        _fetch_json(session, "/api/v1/alerts"),
                        _fetch_json(session, "/api/v1/threats"),
                    )
                    _snapshot_cache = (now, alerts, threats)
            else:
                raions, oblasts, alerts, threats = await asyncio.gather(
                    _fetch_json(session, "/raions.geojson"),
                    _fetch_json(session, "/oblasts.geojson"),
                    _fetch_json(session, "/api/v1/alerts"),
                    _fetch_json(session, "/api/v1/threats"),
                )
                _features(raions)
                _features(oblasts)
                _geometry_cache = (time.monotonic(), raions, oblasts)
                _snapshot_cache = (now, alerts, threats)

        updated_at = _parse_server_time(threats.get("serverTime") if isinstance(threats, dict) else None)
        title = ""
        if region:
            region_key = _feature_key(resolve_map_region(region, oblasts))
            raions, oblasts, alerts, threats, title = regional_payloads(raions, oblasts, alerts, threats, region)
        image = await asyncio.to_thread(render_alert_map, raions, oblasts, alerts, threats, updated_at, title)
        alert_count = len(_alert_keys(alerts, "raions")) + len(_alert_keys(alerts, "oblasts"))
        threat_count = len(_active_threats(threats))
        result = AlertMapResult(image, updated_at, alert_count, threat_count, title)
        if region:
            _regional_cache[region_key] = (now, result)
        else:
            _map_cache = (now, result)
        return result


def _parse_server_time(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _features(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("NEPTUN returned invalid GeoJSON")
    features = payload.get("features")
    if not isinstance(features, list) or not features or len(features) > 1000:
        raise ValueError("NEPTUN returned invalid GeoJSON features")
    return [item for item in features if isinstance(item, dict)]


def _polygons(feature: dict[str, Any]) -> Iterable[list[list[float]]]:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon" and isinstance(coordinates, list):
        if coordinates and isinstance(coordinates[0], list):
            yield coordinates[0]
    elif geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        for polygon in coordinates:
            if isinstance(polygon, list) and polygon and isinstance(polygon[0], list):
                yield polygon[0]


def _valid_points(ring: object) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    if not isinstance(ring, list):
        return result
    for point in ring[:20000]:
        if not isinstance(point, list) or len(point) < 2:
            continue
        try:
            lon, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if 20 <= lon <= 43 and 43 <= lat <= 54:
            result.append((lon, lat))
    return result


def _alert_keys(payload: object, collection: str) -> set[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get(collection), list):
        raise ValueError("NEPTUN returned invalid alert data")
    return {
        str(item.get("key") or "").strip().casefold()
        for item in payload[collection]
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    }


def _active_threats(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("threats"), list):
        raise ValueError("NEPTUN returned invalid threat data")
    return [
        item for item in payload["threats"][:500]
        if isinstance(item, dict) and str(item.get("status") or "active").casefold() == "active"
    ]


def _feature_key(feature: dict[str, Any]) -> str:
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return ""
    return str(properties.get("key") or "").strip().casefold()


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in names:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_alert_map(
    raion_geojson: object,
    oblast_geojson: object,
    alerts: object,
    threats: object,
    updated_at: datetime | None = None,
    region_title: str = "",
) -> bytes:
    """Build a self-contained PNG from already fetched and validated API payloads."""
    raions = [] if region_title and isinstance(raion_geojson, dict) and raion_geojson.get("features") == [] else _features(raion_geojson)
    oblasts = _features(oblast_geojson)
    raion_alerts = _alert_keys(alerts, "raions")
    oblast_alerts = _alert_keys(alerts, "oblasts")
    active_threats = _active_threats(threats)

    all_points = [
        point
        for feature in oblasts
        for ring in _polygons(feature)
        for point in _valid_points(ring)
    ]
    if not all_points:
        raise ValueError("NEPTUN map geometry is empty")
    mean_lat = sum(lat for _, lat in all_points) / len(all_points)
    lon_factor = math.cos(math.radians(mean_lat))
    projected = [(lon * lon_factor, lat) for lon, lat in all_points]
    min_x, max_x = min(x for x, _ in projected), max(x for x, _ in projected)
    min_y, max_y = min(y for _, y in projected), max(y for _, y in projected)

    width, height = 1200, 900
    map_box = (45, 100, 1155, 745)
    box_w, box_h = map_box[2] - map_box[0], map_box[3] - map_box[1]
    scale = min(box_w / (max_x - min_x), box_h / (max_y - min_y))
    offset_x = map_box[0] + (box_w - (max_x - min_x) * scale) / 2
    offset_y = map_box[1] + (box_h - (max_y - min_y) * scale) / 2

    def project(lon: float, lat: float) -> tuple[int, int]:
        x = offset_x + (lon * lon_factor - min_x) * scale
        y = offset_y + (max_y - lat) * scale
        return round(x), round(y)

    image = Image.new("RGB", (width, height), "#101722")
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = _font(34, bold=True), _font(22), _font(18)
    draw.text((45, 30), region_title or "Карта тревог Украины", fill="#f5f7fb", font=title_font)
    stamp = (updated_at or datetime.now(timezone.utc)).astimezone().strftime("%H:%M")
    draw.text((1155, 40), f"обновлено {stamp}", fill="#aeb9c8", font=small_font, anchor="ra")

    def draw_feature(feature: dict[str, Any], fill: str | None, outline: str, line_width: int) -> None:
        for ring in _polygons(feature):
            points = [project(lon, lat) for lon, lat in _valid_points(ring)]
            if len(points) >= 3:
                draw.polygon(points, fill=fill, outline=outline, width=line_width)

    for feature in oblasts:
        active = _feature_key(feature) in oblast_alerts
        draw_feature(feature, "#9d2f3d" if active else "#273548", "#8290a3", 2)
    for feature in raions:
        draw_feature(feature, None, "#44566d", 1)
    for feature in raions:
        if _feature_key(feature) in raion_alerts:
            draw_feature(feature, "#d1464f", "#ffb2b6", 2)
    if region_title:
        draw.text((45, 755), "Детализация: районы. Отдельные статусы громад источник не передаёт.", fill="#aeb9c8", font=small_font)
        for feature in raions:
            points = [p for ring in _polygons(feature) for p in _valid_points(ring)]
            if points:
                x, y = project(sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
                label = str(feature.get("properties", {}).get("rayon", "")).replace(" район", "\nрайон")
                draw.multiline_text((x, y), label, font=small_font, fill="white", anchor="mm", align="center", stroke_width=2, stroke_fill="#101722")

    threat_colors = {
        "uav": "#ffc940", "fpv": "#ffc940", "recon": "#f6a63a",
        "missile": "#ff4e5d", "ballistic": "#ff263d", "kab": "#b78cff",
        "mig31k": "#66b5ff", "unknown": "#e8edf5",
    }
    for threat in active_threats:
        try:
            lon, lat = float(threat.get("lon")), float(threat.get("lat"))
        except (TypeError, ValueError):
            continue
        if not (20 <= lon <= 43 and 43 <= lat <= 54):
            continue
        x, y = project(lon, lat)
        color = threat_colors.get(str(threat.get("type") or "unknown").casefold(), "#e8edf5")
        radius = 8 if threat.get("areaOnly") else 11
        draw.ellipse((x - radius - 3, y - radius - 3, x + radius + 3, y + radius + 3), fill="#101722", outline="#ffffff", width=2)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    legend_y = 785
    legend = [
        ("#d1464f", "воздушная тревога"),
        ("#ffc940", "БПЛА"),
        ("#ff4e5d", "ракета"),
        ("#b78cff", "КАБ"),
        ("#66b5ff", "авиация"),
    ]
    x = 45
    for color, label in legend:
        draw.ellipse((x, legend_y + 3, x + 18, legend_y + 21), fill=color)
        draw.text((x + 27, legend_y), label, fill="#dce3ed", font=body_font)
        x += 27 + int(draw.textlength(label, font=body_font)) + 38
    draw.text(
        (45, 845),
        "Данные: NEPTUN · информационная карта, сверяйтесь с официальными сигналами",
        fill="#8f9cad",
        font=small_font,
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
