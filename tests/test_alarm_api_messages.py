from app.db import Database


def test_alarm_api_tracks_status_and_action_messages_together(tmp_path) -> None:
    db = Database(str(tmp_path / "bot.sqlite3"))
    db.init()
    try:
        chat_id = -100123
        db.upsert_chat(chat_id, "Тревожный чат", "supergroup", None)
        db.set_alarm_api_enabled(chat_id, True, updated_by=1)

        db.set_alarm_api_status_message_id(chat_id, "A", 101)
        db.set_alarm_api_action_message_id(chat_id, "A", 102)
        db.set_alarm_api_status_message_id(chat_id, "N", 201)
        db.set_alarm_api_action_message_id(chat_id, "N", 202)

        assert db.alarm_api_status_message_ids(chat_id, "A") == [101, 102]
        assert db.alarm_api_status_message_ids(chat_id, "N") == [201, 202]

        db.clear_alarm_api_status_message_ids(chat_id, "A")

        assert db.alarm_api_status_message_ids(chat_id, "A") == []
        assert db.alarm_api_status_message_ids(chat_id, "N") == [201, 202]
    finally:
        db.close()
