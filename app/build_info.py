"""Stamp the image at build time; report that immutable stamp at runtime."""
import argparse
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_revision(root: Path) -> str | None:
    git_dir = root / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            if not ref.startswith("refs/") or ".." in Path(ref).parts:
                return None
            loose = git_dir / ref
            if loose.is_file():
                head = loose.read_text(encoding="ascii").strip()
            else:
                packed = (git_dir / "packed-refs").read_text(encoding="ascii")
                head = next((line.split()[0] for line in packed.splitlines() if len(line.split()) == 2 and line.split()[1] == ref), "")
        return head.lower() if re.fullmatch(r"[0-9a-fA-F]{40,64}", head) else None
    except (OSError, UnicodeError):
        return None


def create_stamp(root: Path) -> dict:
    return {"revision": git_revision(root), "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@lru_cache(maxsize=1)
def get_build_info() -> dict:
    path = Path(__file__).with_name("build-info.json")
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stamp = {"revision": git_revision(Path(__file__).resolve().parent.parent), "builtAt": None}
    revision = stamp.get("revision")
    return {"revision": revision, "shortRevision": revision[:7] if revision else "не определена",
            "builtAt": stamp.get("builtAt"), "startedAt": STARTED_AT,
            "source": "image" if path.is_file() else "local"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(create_stamp(args.source)), encoding="utf-8")
