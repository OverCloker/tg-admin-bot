#!/usr/bin/env python3
"""Send an encrypted, consistent SQLite backup to the owner's private Telegram chat.

Only the age/SSH public recipient key is stored on the VPS. The decryption key
must remain elsewhere. No database, token, or decrypted archive is logged.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
RECIPIENT_FILE = Path("/etc/otveto4ka-backup/recipient.pub")
MAX_DOCUMENT_BYTES = 45 * 1024 * 1024


class BackupError(RuntimeError):
    pass


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def configuration() -> tuple[str, int]:
    if os.geteuid() != 0:
        raise BackupError("Run this backup as root (sudo or systemd).")
    env_file = PROJECT_DIR / ".env"
    if not env_file.is_file():
        raise BackupError("Missing project .env file.")
    env = read_env(env_file)
    token = env.get("BOT_TOKEN", "")
    owner = env.get("OWNER_ID", "")
    if env.get("BOT_API_URL", "https://api.telegram.org").rstrip("/") != "https://api.telegram.org":
        raise BackupError("This host-side backup requires the public Telegram Bot API.")
    if not token or ":" not in token or not owner.isdecimal() or int(owner) <= 0:
        raise BackupError("BOT_TOKEN or positive OWNER_ID is missing from .env.")
    if not RECIPIENT_FILE.is_file():
        raise BackupError(f"Missing public encryption key: {RECIPIENT_FILE}")
    recipient = RECIPIENT_FILE.read_text(encoding="utf-8").strip()
    if not (recipient.startswith("age1") or recipient.startswith("ssh-ed25519 ")):
        raise BackupError("Recipient must be an age or ssh-ed25519 public key.")
    for command in ("age", "docker"):
        if not shutil.which(command):
            raise BackupError(f"Missing required command: {command}")
    return token, int(owner)


def run(*args: str) -> str:
    result = subprocess.run(
        args, cwd=PROJECT_DIR, capture_output=True, text=True, check=False
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise BackupError(f"{args[0]} failed (exit {result.returncode}): "
                          f"{detail[-1] if detail else 'no diagnostic'}")
    return result.stdout.strip()


def telegram(token: str, method: str, payload: bytes, content_type: str) -> dict:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=payload,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as exc:
        raise BackupError(f"Telegram {method} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BackupError(f"Telegram {method} could not be reached: {type(exc).__name__}") from None
    if not answer.get("ok"):
        raise BackupError(f"Telegram {method} rejected the request: "
                          f"{answer.get('description', 'unknown error')}")
    return answer["result"]


def private_chat(token: str, owner: int) -> None:
    payload = urllib.parse.urlencode({"chat_id": owner}).encode()
    chat = telegram(token, "getChat", payload, "application/x-www-form-urlencoded")
    if chat.get("type") != "private" or chat.get("id") != owner:
        raise BackupError("OWNER_ID does not resolve to the owner's private chat.")


def send_message(token: str, owner: int, message: str) -> None:
    payload = urllib.parse.urlencode({"chat_id": owner, "text": message}).encode()
    telegram(token, "sendMessage", payload, "application/x-www-form-urlencoded")


def send_document(token: str, owner: int, path: Path, caption: str) -> None:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise BackupError("Encrypted backup exceeds the safe 45 MiB Bot API limit.")
    boundary = f"otveto4ka-{secrets.token_hex(16)}"
    fields = {"chat_id": str(owner), "caption": caption}
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.extend(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
        f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
    )
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    result = telegram(token, "sendDocument", bytes(body), f"multipart/form-data; boundary={boundary}")
    chat = result.get("chat", {})
    document = result.get("document", {})
    if chat.get("type") != "private" or chat.get("id") != owner or document.get("file_name") != path.name:
        raise BackupError("Telegram response did not confirm the private-chat document.")


def create_container_backup() -> str:
    code = (
        "import os,sqlite3,uuid; from datetime import datetime,timezone; "
        "from pathlib import Path; "
        "source=Path(os.environ['DB_PATH']); "
        "directory=source.parent/'backups'; directory.mkdir(mode=0o700,exist_ok=True); "
        "target=directory/('telegram-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sqlite3'); "
        "src=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True); "
        "dst=sqlite3.connect(target); src.backup(dst); dst.close(); src.close(); "
        "check=sqlite3.connect(target); result=check.execute('PRAGMA quick_check').fetchone()[0]; check.close(); "
        "os.chmod(target,0o600); "
        "assert result=='ok', 'SQLite quick_check failed'; print(target)"
    )
    path = run("docker", "compose", "exec", "-T", "--user", "10001:10001", "api", "python", "-c", code)
    if not path.startswith("/data/backups/telegram-") or not path.endswith(".sqlite3"):
        raise BackupError("Unexpected backup path returned by container.")
    return path


def remove_container_backup(path: str) -> None:
    code = "import pathlib,sys; pathlib.Path(sys.argv[1]).unlink(missing_ok=True)"
    run("docker", "compose", "exec", "-T", "--user", "10001:10001", "api", "python", "-c", code, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate configuration; do not send data")
    args = parser.parse_args()
    token: str | None = None
    owner: int | None = None
    remote_path: str | None = None
    try:
        token, owner = configuration()
        if args.check:
            print("Backup configuration: ready (no data sent).")
            return 0
        private_chat(token, owner)
        with tempfile.TemporaryDirectory(prefix="otveto4ka-backup-") as directory:
            tmp = Path(directory)
            os.chmod(tmp, 0o700)
            remote_path = create_container_backup()
            plain = tmp / "bot.sqlite3"
            run("docker", "compose", "cp", f"api:{remote_path}", str(plain))
            os.chmod(plain, 0o600)
            if plain.stat().st_size == 0:
                raise BackupError("Database backup is empty.")
            compressed = tmp / "bot.sqlite3.gz"
            with plain.open("rb") as source, gzip.open(compressed, "wb", compresslevel=6) as target:
                shutil.copyfileobj(source, target)
            plain.unlink()
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
            encrypted = tmp / f"otveto4ka-db-{stamp}.sqlite3.gz.age"
            run("age", "-R", str(RECIPIENT_FILE), "-o", str(encrypted), str(compressed))
            compressed.unlink()
            if encrypted.stat().st_size == 0:
                raise BackupError("Encrypted backup is empty.")
            send_document(token, owner, encrypted, f"База бота · {stamp} · SQLite quick_check: ok")
            print(f"Encrypted SQLite backup delivered to owner's private chat ({encrypted.stat().st_size} bytes).")
        return 0
    except (BackupError, OSError, ValueError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        if token and owner and not args.check:
            try:
                private_chat(token, owner)
                send_message(token, owner, "⚠️ Автоматическая резервная копия базы не создана или не отправлена. Проверь журнал otveto4ka-telegram-backup.service.")
            except BackupError:
                pass
        return 1
    finally:
        if remote_path:
            try:
                remove_container_backup(remote_path)
            except BackupError as exc:
                print(f"Warning: could not remove temporary container backup: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
