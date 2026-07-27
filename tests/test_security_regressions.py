import asyncio
import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.admin_api import PinnedPublicResolver, resolve_public_stream_url
from app.db import Database
from app.staff import StaffService
from app.media_tasks import MediaTaskService
from app.youtube_media import validate_supported_media_url


class SecurityRegressionTests(unittest.TestCase):
    def make_db(self):
        temporary = tempfile.TemporaryDirectory()
        db = Database(str(Path(temporary.name) / "test.sqlite3"))
        db.init()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(db.close)
        return db

    def test_media_url_requires_exact_supported_host(self):
        self.assertIsNotNone(validate_supported_media_url("https://www.youtube.com/watch?v=test"))
        self.assertIsNone(validate_supported_media_url("https://www.youtube.com.evil.test/watch?v=test"))
        self.assertIsNone(validate_supported_media_url("https://www.youtube.com@127.0.0.1/watch?v=test"))
        self.assertIsNone(validate_supported_media_url("http://127.0.0.1/youtube.com/watch?v=test"))

    def test_radio_stream_uses_only_prevalidated_pinned_addresses(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80)),
        ]
        with patch("app.admin_api.socket.getaddrinfo", return_value=answers):
            checked, hostname, addresses = resolve_public_stream_url("http://radio.example/stream")
        self.assertEqual(checked, "http://radio.example/stream")
        self.assertEqual(hostname, "radio.example")
        self.assertEqual(addresses, ("93.184.216.34",))
        resolver = PinnedPublicResolver(hostname, addresses)
        records = asyncio.run(resolver.resolve("radio.example", 80, socket.AF_UNSPEC))
        self.assertEqual([record["host"] for record in records], ["93.184.216.34"])
        with self.assertRaises(OSError):
            asyncio.run(resolver.resolve("different.example", 80, socket.AF_UNSPEC))

    def test_login_request_can_create_only_one_session(self):
        db = self.make_db()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
        db.create_user_login_request("login", "secret", expires)
        self.assertTrue(db.approve_user_login("login", 42, "tester", "Tester"))
        self.assertTrue(db.consume_user_login_and_create_session("login", "secret", "token-1", 42, "tester", "Tester", expires))
        self.assertFalse(db.consume_user_login_and_create_session("login", "secret", "token-2", 42, "tester", "Tester", expires))
        count = db._conn.execute("select count(*) from user_sessions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_cross_chat_ad_delete_does_not_remove_attachments(self):
        db = self.make_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for chat_id in (1, 2):
            db._conn.execute(
                "insert into chats(chat_id,title,type,updated_at) values(?,?,?,?)",
                (chat_id, str(chat_id), "supergroup", now),
            )
        columns = (
            "chat_id,text,enabled,start_time,interval_minutes,duration_type,start_mode,"
            "created_at,updated_at"
        )
        db._conn.execute(
            f"insert into advertisements({columns}) values(?,?,?,?,?,?,?,?,?)",
            (2, "victim", 1, "00:00", 60, "forever", "manual", now, now),
        )
        ad_id = db._conn.execute("select id from advertisements where chat_id=2").fetchone()[0]
        db._conn.execute(
            "insert into advertisement_attachments(advertisement_id,media_type,file_id) values(?,?,?)",
            (ad_id, "photo", "file"),
        )
        db._conn.commit()
        self.assertFalse(db.delete_advertisement(1, ad_id))
        count = db._conn.execute(
            "select count(*) from advertisement_attachments where advertisement_id=?", (ad_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_roll_mute_cooldown_is_claimed_atomically(self):
        db = self.make_db()
        now = datetime.now(timezone.utc)
        used_at = now.isoformat(timespec="seconds")
        cutoff = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        self.assertTrue(db.claim_roll_mute(1, used_at, cutoff))
        self.assertFalse(db.claim_roll_mute(1, used_at, cutoff))

    def test_alarm_notifications_keep_one_configured_topic(self):
        db = self.make_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db._conn.execute(
            "insert into chats(chat_id,title,type,updated_at) values(?,?,?,?)",
            (-100, "Alarm chat", "supergroup", now),
        )
        db._conn.commit()
        self.assertIsNone(db.get_alarm_settings(-100).alarm_thread_id)
        db.set_alarm_thread(-100, 77, 42)
        self.assertEqual(db.get_alarm_settings(-100).alarm_thread_id, 77)
        db.set_alarm_thread(-100, None, 42)
        self.assertIsNone(db.get_alarm_settings(-100).alarm_thread_id)

    def test_dig_star_purchase_is_applied_once(self):
        db = self.make_db()
        db.register_dig_player(0, 42, "tester", "Tester")
        purchase = dict(
            user_id=42, username="tester", full_name="Tester", chat_id=123,
            amount=3, currency="XTR", charge_id="charge-1", action="item",
            item_key="star_lucky_dig", quantity=3,
        )
        self.assertTrue(db.apply_dig_star_purchase_once(**purchase))
        self.assertFalse(db.apply_dig_star_purchase_once(**purchase))
        quantity = db._conn.execute(
            "select quantity from dig_items where chat_id=0 and user_id=42 and item_key='star_lucky_dig'"
        ).fetchone()[0]
        self.assertEqual(quantity, 3)
        self.assertEqual(db._conn.execute("select count(*) from star_payments where charge_id='charge-1'").fetchone()[0], 1)

    def test_pending_paid_message_can_be_claimed_once(self):
        db = self.make_db()
        db.save_pending_star_message("payload", 42, -100, "hello")
        self.assertIsNotNone(db.claim_pending_star_message("payload"))
        self.assertIsNone(db.claim_pending_star_message("payload"))

    def test_secret_message_flow_keeps_text_out_of_group_payload(self):
        db = self.make_db()
        db.save_secret_message_compose("compose-1", 10, -100, 20, "@target")
        compose = db.get_secret_message_compose_for_sender(10)
        self.assertIsNotNone(compose)
        self.assertEqual(compose.target_id, 20)

        db.save_secret_message(
            message_id="secret-1",
            chat_id=compose.chat_id,
            sender_id=10,
            sender_username="sender",
            sender_name="Sender",
            target_id=compose.target_id,
            target_name=compose.target_name,
            text="hidden text",
        )
        db.delete_secret_message_compose(compose.compose_id)
        self.assertIsNone(db.get_secret_message_compose_for_sender(10))

        secret = db.get_secret_message("secret-1")
        self.assertEqual(secret.text, "hidden text")
        self.assertEqual(secret.target_id, 20)
        self.assertIsNone(secret.delivered_at)
        db.mark_secret_message_delivered("secret-1")
        self.assertIsNotNone(db.get_secret_message("secret-1").delivered_at)

    def test_media_cleanup_never_deletes_outside_storage_roots(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        db_path = str(Path(temporary.name) / "media.sqlite3")
        service = MediaTaskService(db_path)
        self.addCleanup(service.close)
        outside = Path(temporary.name) / "keep.txt"
        outside.write_text("keep", encoding="utf-8")
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
        service._conn.execute(
            """
            insert into media_tasks(user_id,task_type,source_file_path,status,priority,file_size_bytes,created_at,finished_at)
            values(?,?,?,?,?,?,?,?)
            """,
            (1, "audio_convert", str(outside), "completed", 10, 4, old, old),
        )
        service._conn.commit()
        service.cleanup_stale_files(24)
        self.assertTrue(outside.is_file())

    def test_non_owner_cannot_reroute_staff_topic(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        service = StaffService(str(Path(temporary.name) / "staff.sqlite3"), owner_id=1)
        self.addCleanup(service.close)
        service.db.set_setting("staff_chat_id", "100")
        service.db.set_setting("staff_topic_logs", "10")
        message = SimpleNamespace(
            chat=SimpleNamespace(id=100),
            message_thread_id=99,
            from_user=SimpleNamespace(id=2),
            forum_topic_created=None,
            forum_topic_edited=SimpleNamespace(name="логи"),
            reply_to_message=None,
        )
        service.observe_message(message)
        self.assertEqual(service.topic_id("logs"), 10)


if __name__ == "__main__":
    unittest.main()
