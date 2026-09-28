import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("server_telegram_backup", ROOT / "server-telegram-backup.py")
backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backup
SPEC.loader.exec_module(backup)


def test_read_env_does_not_execute_shell(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN='123:abc'\nOWNER_ID=42\nIGNORED=$(touch /tmp/no-such-file)\n", encoding="utf-8")
    assert backup.read_env(env)["BOT_TOKEN"] == "123:abc"
    assert backup.read_env(env)["OWNER_ID"] == "42"


def test_configuration_requires_private_owner_and_public_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("BOT_TOKEN=123:abc\nOWNER_ID=-100123\n", encoding="utf-8")
    recipient = tmp_path / "recipient.pub"
    recipient.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtest backup\n", encoding="utf-8")
    monkeypatch.setattr(backup, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(backup, "RECIPIENT_FILE", recipient)
    monkeypatch.setattr(backup.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(backup.shutil, "which", lambda command: "/bin/" + command)
    with pytest.raises(backup.BackupError, match="positive OWNER_ID"):
        backup.configuration()
    (tmp_path / ".env").write_text("BOT_TOKEN=123:abc\nOWNER_ID=42\n", encoding="utf-8")
    assert backup.configuration() == ("123:abc", 42)


def test_send_document_requires_private_chat_confirmation(tmp_path, monkeypatch):
    encrypted = tmp_path / "test.sqlite3.age"
    encrypted.write_bytes(b"age-encryption.org/v1\nexample")
    calls = []

    def fake_telegram(token, method, payload, content_type):
        calls.append((method, payload, content_type))
        return {"chat": {"type": "group", "id": -42}, "document": {"file_name": encrypted.name}}

    monkeypatch.setattr(backup, "telegram", fake_telegram)
    with pytest.raises(backup.BackupError, match="private-chat"):
        backup.send_document("123:abc", 42, encrypted, "test")
    assert calls[0][0] == "sendDocument"
    assert encrypted.read_bytes() in calls[0][1]


def test_main_cleans_container_copy_after_success(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "configuration", lambda: ("123:abc", 42))
    monkeypatch.setattr(backup, "private_chat", lambda *_: None)
    monkeypatch.setattr(backup, "create_container_backup", lambda: "/data/backups/telegram-test.sqlite3")
    removed = []
    sent = []
    monkeypatch.setattr(backup, "remove_container_backup", removed.append)
    monkeypatch.setattr(backup, "send_document", lambda token, owner, path, caption: sent.append(path.read_bytes()))

    def fake_run(*args):
        if args[1:3] == ("compose", "cp"):
            Path(args[-1]).write_bytes(b"SQLite data")
        elif args[0] == "age":
            Path(args[4]).write_bytes(b"age-encryption.org/v1\n")
        return ""

    monkeypatch.setattr(backup, "run", fake_run)
    monkeypatch.setattr(backup, "RECIPIENT_FILE", tmp_path / "recipient.pub")
    monkeypatch.setattr(sys, "argv", ["server-telegram-backup.py"])
    assert backup.main() == 0
    assert sent == [b"age-encryption.org/v1\n"]
    assert removed == ["/data/backups/telegram-test.sqlite3"]


def test_installer_validates_before_enabling_timer():
    script = (ROOT / "server-install-telegram-backup.sh").read_text(encoding="utf-8")
    assert script.index("--check") < script.index('enable --now "$TIMER_NAME"')
    assert "Persistent=true" in script
    assert "UMask=0077" in script
