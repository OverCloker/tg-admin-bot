import json

from app.alerts_diagnostics import save_alerts_response


def test_capture_preserves_payload_and_redacts_token(tmp_path):
    payload = {"alerts": [{"location_uid": "46", "threats": [{"threat_type": "drones"}]},
                          {"location_uid": 9}, {"location_uid": "10"}],
               "notes": "secret-token"}
    save_alerts_response(str(tmp_path / "bot.sqlite3"), 200, payload, "date", "secret-token")
    save_alerts_response(str(tmp_path / "bot.sqlite3"), 304, None, "date", "secret-token")
    raw = (tmp_path / "alerts-diagnostics/responses.jsonl").read_text(encoding="utf-8")
    assert "secret-token" not in raw
    first, second = map(json.loads, raw.splitlines())
    assert first["payload"]["alerts"] == payload["alerts"]
    assert len(first["locations_46_9"]) == 2
    assert first["received_at_utc"].endswith("+00:00")
    assert first["payload_sha256"]
    assert second["http_status"] == 304 and second["payload"] is None


def test_capture_failure_does_not_break_alerts(tmp_path):
    (tmp_path / "alerts-diagnostics").write_text("not a directory")
    save_alerts_response(str(tmp_path / "bot.sqlite3"), 200, {}, None, "token")
