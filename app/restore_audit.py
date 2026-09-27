"""Offline, read-only verification of a restored database and deployed code."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from .db import Database


def code_digest(root: Path) -> str:
    paths = sorted(path for path in (root / "app").rglob("*.py") if "__pycache__" not in path.parts)
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def schema(connection: sqlite3.Connection) -> dict:
    tables = {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        quoted = name.replace('"', '""')
        tables[name] = {row[1]: (row[2].upper(), row[5]) for row in connection.execute(f'PRAGMA table_info("{quoted}")')}
    return tables


def audit_database(path: Path) -> dict:
    # Never initialise or repair the production database in this audit.
    with tempfile.TemporaryDirectory(prefix="bot-schema-") as directory:
        reference = Database(str(Path(directory) / "reference.sqlite3"))
        try:
            reference.init()
            expected = schema(reference._conn)
            expected_indexes = {row[0] for row in reference._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
        finally:
            reference.close()
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as actual:
        actual.execute("PRAGMA query_only=ON")
        found = schema(actual)
        issues = []
        found_indexes = {row[0] for row in actual.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
        issues.extend(f"missing index: {name}" for name in sorted(expected_indexes - found_indexes))
        for table, columns in expected.items():
            if table not in found:
                issues.append(f"missing table: {table}")
                continue
            for column, definition in columns.items():
                if column not in found[table]:
                    issues.append(f"missing column: {table}.{column}")
                elif found[table][column] != definition:
                    issues.append(f"column type/key mismatch: {table}.{column}")
        integrity = [row[0] for row in actual.execute("PRAGMA integrity_check")]
        violations = actual.execute("PRAGMA foreign_key_check").fetchall()
        foreign_keys = len(violations)
        relationships = {f"{table}->{parent}": count for (table, parent), count in
                         Counter((row[0], row[2]) for row in violations).items()}
    return {"integrity": integrity, "foreignKeyViolations": foreign_keys,
            "relationshipWarnings": relationships,
            "expectedTables": len(expected), "actualTables": len(found), "schemaIssues": issues,
            "schemaOk": not issues,
            "ok": integrity == ["ok"] and not foreign_keys and not issues}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    result = audit_database(args.database)
    result["appCodeDigest"] = code_digest(Path(__file__).resolve().parent.parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
