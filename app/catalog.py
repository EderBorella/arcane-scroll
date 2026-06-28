"""In-memory catalog. Loads the whole SQLite store into memory once at startup; the rest of the
service reads from here (never per-request DB hits). Data lives outside the repo, at ARCANE_DB_PATH."""
import json
import os
import sqlite3


class Catalog:
    """entries: {kind: {idx: record}} ; catalog: {name: value}."""

    def __init__(self, db_path: str):
        self.entries: dict[str, dict[str, dict]] = {}
        self.catalog: dict[str, object] = {}
        con = sqlite3.connect(db_path)
        try:
            for kind, idx, data in con.execute("SELECT kind, idx, data FROM entries"):
                self.entries.setdefault(kind, {})[idx] = json.loads(data)
            for name, data in con.execute("SELECT name, data FROM catalog"):
                self.catalog[name] = json.loads(data)
        finally:
            con.close()

    def stats(self) -> dict:
        return {
            "entries": {k: len(v) for k, v in sorted(self.entries.items())},
            "entries_total": sum(len(v) for v in self.entries.values()),
            "catalog": len(self.catalog),
        }


def load() -> Catalog:
    db_path = os.environ.get("ARCANE_DB_PATH")
    if not db_path:
        raise RuntimeError("ARCANE_DB_PATH is not set")
    return Catalog(db_path)
