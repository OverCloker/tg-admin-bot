from datetime import datetime, timedelta, timezone

from app.bot import giveaway_pick_date


def test_giveaway_pick_date_resets_at_0001_kyiv_time() -> None:
    kyiv = timezone(timedelta(hours=3))

    assert giveaway_pick_date(datetime(2026, 8, 22, 0, 0, 59, tzinfo=kyiv)) == "2026-08-21"
    assert giveaway_pick_date(datetime(2026, 8, 22, 0, 1, 0, tzinfo=kyiv)) == "2026-08-22"
    assert giveaway_pick_date(datetime(2026, 8, 22, 23, 59, 0, tzinfo=kyiv)) == "2026-08-22"


def test_giveaway_pick_date_converts_to_kyiv_time() -> None:
    assert giveaway_pick_date(datetime(2026, 8, 21, 21, 1, 0, tzinfo=timezone.utc)) == "2026-08-22"
    assert giveaway_pick_date(datetime(2026, 8, 21, 21, 0, 59, tzinfo=timezone.utc)) == "2026-08-21"
