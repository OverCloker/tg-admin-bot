"""Persistent, public media snapshots used by Telegram inline results."""

from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from PIL import Image


INLINE_MEDIA_DIRECTORY = Path("media_storage") / "inline_maps"
INLINE_MEDIA_MAX_FILES = 128
INLINE_MEDIA_MAX_AGE_SECONDS = 24 * 60 * 60
INLINE_PHOTO_MAX_BYTES = 5 * 1024 * 1024
INLINE_PHOTO_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")
_SAVE_LOCK = threading.Lock()


def public_api_base_url() -> str:
    """Return the public HTTPS origin of the API that serves inline photos."""
    configured = os.getenv("ADMIN_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        return configured
    miniapp = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if miniapp.endswith("/miniapp"):
        return miniapp[: -len("/miniapp")]
    if miniapp:
        parts = urlsplit(miniapp)
        return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return ""


def inline_photo_url(filename: str) -> str:
    base = public_api_base_url()
    if not base.lower().startswith("https://") or not INLINE_PHOTO_RE.fullmatch(filename):
        return ""
    return f"{base}/inline-media/{filename}"


def _jpeg_bytes(image: bytes) -> bytes:
    with Image.open(io.BytesIO(image)) as source:
        converted = source.convert("RGB")
        for quality in (88, 78, 68, 58):
            output = io.BytesIO()
            converted.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
            if output.tell() <= INLINE_PHOTO_MAX_BYTES:
                return output.getvalue()
        converted.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        converted.save(output, format="JPEG", quality=70, optimize=True, progressive=True)
        if output.tell() > INLINE_PHOTO_MAX_BYTES:
            raise ValueError("inline JPEG exceeds Telegram's 5 MB limit")
        return output.getvalue()


def _cleanup(directory: Path, keep: Path) -> None:
    now = time.time()
    files = sorted(
        (item for item in directory.glob("*.jpg") if item.is_file() and INLINE_PHOTO_RE.fullmatch(item.name)),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for index, item in enumerate(files):
        if item == keep:
            continue
        try:
            if index >= INLINE_MEDIA_MAX_FILES or now - item.stat().st_mtime > INLINE_MEDIA_MAX_AGE_SECONDS:
                item.unlink(missing_ok=True)
        except OSError:
            # Cleanup is best-effort; failing to remove an old snapshot must not
            # prevent delivery of the current alert map.
            pass


def save_inline_photo(image: bytes, directory: Path | None = None) -> tuple[str, Path]:
    """Save an immutable JPEG and return its public filename and path."""
    jpeg = _jpeg_bytes(image)
    filename = f"{hashlib.sha256(jpeg).hexdigest()[:32]}.jpg"
    root = directory or INLINE_MEDIA_DIRECTORY
    root.mkdir(parents=True, exist_ok=True)
    target = root / filename
    with _SAVE_LOCK:
        if not target.exists():
            with tempfile.NamedTemporaryFile(dir=root, prefix=f".{filename}.", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(jpeg)
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        _cleanup(root, target)
    return filename, target


def resolve_inline_photo(filename: str, directory: Path | None = None) -> Path | None:
    """Resolve only generated filenames; never expose arbitrary filesystem paths."""
    if not INLINE_PHOTO_RE.fullmatch(filename):
        return None
    path = (directory or INLINE_MEDIA_DIRECTORY) / filename
    return path if path.is_file() else None
