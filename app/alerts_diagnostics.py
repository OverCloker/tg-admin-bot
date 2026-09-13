"""Bounded, token-free capture of Alerts.in.ua responses for incident comparison."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


def save_alerts_response(db_path: str, status: int, payload: object,
                         last_modified: str | None, token: str) -> None:
    try:
        directory = Path(db_path).resolve().parent / "alerts-diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        # Capture response data only; never request URLs or Authorization headers.
        serialized = json.dumps(payload, ensure_ascii=False)
        if token:
            serialized = serialized.replace(token, "[REDACTED]")
            last_modified = (last_modified or "").replace(token, "[REDACTED]")
        safe_payload = json.loads(serialized)
        alerts = safe_payload.get("alerts", []) if isinstance(safe_payload, dict) else []
        record = {
            "received_at_utc": datetime.now(timezone.utc).isoformat(),
            "http_status": status,
            "last_modified": last_modified,
            "payload_sha256": hashlib.sha256(serialized.encode()).hexdigest() if status == 200 else None,
            "locations_46_9": [item for item in alerts if isinstance(item, dict)
                               and str(item.get("location_uid")) in {"46", "9"}],
            "payload": safe_payload,
        }
        line = json.dumps(record, ensure_ascii=False)
        # Four backups plus the active file: about 50 MB maximum.
        handler = RotatingFileHandler(directory / "responses.jsonl", maxBytes=10_000_000,
                                      backupCount=4, encoding="utf-8")
        try:
            handler.emit(logging.LogRecord("alerts_capture", logging.INFO, "", 0, line, (), None))
        finally:
            handler.close()
    except Exception:
        # A full disk or bad permissions must not interrupt alarm delivery.
        logging.warning("Could not save Alerts.in.ua diagnostic response")
