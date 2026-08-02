from pathlib import Path


TEXT_ROOTS = (Path("app"), Path("tests"))
TEXT_SUFFIXES = {".py"}
MOJIBAKE_MARKERS = (
    "р" + "џ",
    "в" + "›",
    "в" + "ќ",
    "в" + "Ђ",
    "Г" + "—",
)


def test_python_sources_are_utf8_without_common_mojibake() -> None:
    offenders: list[str] = []
    for root in TEXT_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in TEXT_SUFFIXES or "__pycache__" in path.parts:
                continue
            data = path.read_bytes()
            assert not data.startswith(b"\xef\xbb\xbf"), f"{path} has UTF-8 BOM"
            text = data.decode("utf-8")
            for marker in MOJIBAKE_MARKERS:
                if marker in text:
                    offenders.append(f"{path}: {marker}")
    assert offenders == []
