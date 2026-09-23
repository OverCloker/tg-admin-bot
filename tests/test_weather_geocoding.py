import asyncio

import pytest

from app.weather_geo import (
    format_nominatim_place,
    local_weather_place,
    nominatim_result_is_settlement,
    open_meteo_result_is_settlement,
    resolve_weather_place,
)


@pytest.mark.parametrize(
    ("query", "expected_name", "latitude", "longitude"),
    [
        ("Авангард Днепр", "Авангард", 48.010278, 33.316111),
        ("пгт Авангард Днепропетровская область", "Авангард", 48.010278, 33.316111),
        ("Марьяновка Криворожский район", "Марьяновка", 47.999444, 33.293333),
        ("село Мар'янівка", "Мар'янівка", 47.999444, 33.293333),
    ],
)
def test_local_kryvyi_rih_settlements(query, expected_name, latitude, longitude):
    place = local_weather_place(query)
    assert place is not None
    assert place.label.startswith(expected_name)
    assert place.latitude == latitude
    assert place.longitude == longitude


def test_street_query_never_uses_settlement_fallback():
    assert local_weather_place("улица Авангард Днепр") is None
    with pytest.raises(RuntimeError, match="settlement required"):
        asyncio.run(resolve_weather_place(object(), "улица Авангард Днепр"))


def test_local_fallback_does_not_hijack_same_name_in_another_region():
    assert local_weather_place("Марьяновка Одесская область") is None
    assert local_weather_place("Авангард Киев") is None


def test_nominatim_accepts_settlements_and_rejects_addresses():
    village = {
        "type": "village",
        "addresstype": "village",
        "name": "Марьяновка",
        "address": {
            "village": "Марьяновка",
            "county": "Криворожский район",
            "state": "Днепропетровская область",
            "postcode": "50000",
            "country": "Украина",
        },
    }
    street = {
        "type": "residential",
        "addresstype": "road",
        "name": "улица Авангард",
        "address": {"city": "Днепр"},
    }
    assert nominatim_result_is_settlement(village) is True
    assert nominatim_result_is_settlement(street) is False
    label = format_nominatim_place(village, "Марьяновка")
    assert label == "Марьяновка, Криворожский район, Днепропетровская область, Украина"
    assert "50000" not in label


def test_open_meteo_accepts_only_populated_places():
    assert open_meteo_result_is_settlement({"feature_code": "PPL"}) is True
    assert open_meteo_result_is_settlement({"feature_code": "PPLA2"}) is True
    assert open_meteo_result_is_settlement({"feature_code": "ADM2"}) is False
    assert open_meteo_result_is_settlement({}) is False
