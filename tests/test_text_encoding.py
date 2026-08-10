from pathlib import Path


TEXT_ROOTS = (Path("app"), Path("tests"))
TEXT_SUFFIXES = {".cmd", ".css", ".html", ".ini", ".js", ".json", ".md", ".ps1", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00d0",
    "\u00d1",
    "\u00c2",
    "\u00c3",
    "\u00e2\u20ac",
    "\u0420\u045f",
    "\u0420\u0402",
    "\u0420\u0403",
    "\u0420\u0490",
    "\u0420\u0491",
    "\u0421\u0453",
    "\u0440\u045f",
    "\u0432\u0402",
    "\u0432\u045c",
    "\u0412\u00ab",
    "\u0412\u00bb",
    "\u0413\u2014",
)


def test_text_sources_are_utf8_without_common_mojibake() -> None:
    offenders: list[str] = []
    paths = [path for root in TEXT_ROOTS for path in root.rglob("*")]
    paths.extend(path for path in Path(".").iterdir() if path.is_file())
    for path in paths:
        if path.suffix.lower() not in TEXT_SUFFIXES or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), f"{path} has UTF-8 BOM"
        text = data.decode("utf-8")
        for marker in MOJIBAKE_MARKERS:
            if marker in text:
                offenders.append(f"{path}: {marker}")
    assert offenders == []
