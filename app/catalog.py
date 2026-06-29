"""Shared resource catalog — the single in-memory copy of the reference data the whole service reads
from. Loaded ONCE at startup from the local store (ARCANE_DB_PATH); no per-request DB access.

Deliberately GENERIC and data-free: it exposes entity *records* by kind and supplemental *lists* by
name, addressed as strings, so no specific content lives in this (committed) code — only the access
machinery. The values live in the local store.

    records(kind)       -> {idx: record}    entity collections (e.g. "spells", "classes", "levels")
    record(kind, idx)   -> record | None
    by_name(kind)       -> {norm_name: record}   name-keyed view (for name-based lookups/validation)
    get(name[, default])-> value             supplemental tables / enums / lists, by name
    require(name)       -> value             same, raises if absent
    kinds / names       -> sorted keys
    stats()             -> summary

Load once at startup via load(); read anywhere via get_catalog()."""
import json
import os
import re
import sqlite3
from typing import Any


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class Catalog:
    def __init__(self, db_path: str):
        self._records: dict[str, dict[str, dict]] = {}
        self._lists: dict[str, Any] = {}
        self._by_name: dict[str, dict[str, dict]] = {}
        try:
            con = sqlite3.connect(db_path)
            try:
                for kind, idx, data in con.execute("SELECT kind, idx, data FROM entries"):
                    self._records.setdefault(kind, {})[idx] = json.loads(data)
                for name, data in con.execute("SELECT name, data FROM catalog"):
                    self._lists[name] = json.loads(data)
            finally:
                con.close()
        except (sqlite3.Error, json.JSONDecodeError) as e:
            raise RuntimeError(f"failed to load catalog from {db_path!r}: {e}") from e

    # -- entity records, by kind --
    def records(self, kind: str) -> dict[str, dict]:
        """All records of a kind, keyed by index."""
        return self._records.get(kind, {})

    def record(self, kind: str, idx: str) -> dict | None:
        return self._records.get(kind, {}).get(idx)

    def by_name(self, kind: str) -> dict[str, dict]:
        """Records of a kind keyed by normalized name (cached)."""
        view = self._by_name.get(kind)
        if view is None:
            view = {_norm(r.get("name", "")): r for r in self.records(kind).values()}
            self._by_name[kind] = view
        return view

    @property
    def kinds(self) -> list[str]:
        return sorted(self._records)

    # -- supplemental lists / tables / enums, by name --
    def get(self, name: str, default: Any = None) -> Any:
        return self._lists.get(name, default)

    def require(self, name: str) -> Any:
        try:
            return self._lists[name]
        except KeyError:
            raise KeyError(f"catalog list {name!r} not loaded") from None

    # -- versioned prompts: return the active version's text for a locator --
    def prompt(self, locator: str) -> str:
        """Active prompt text for a locator. Prompts are versioned in the `prompts` records table;
        superseded versions are kept (with a comment) for history but never returned here."""
        for r in self.records("prompts").values():
            if r.get("locator") == locator and r.get("active"):
                text = r.get("text", "")
                if not text:
                    raise KeyError(f"active prompt for locator {locator!r} has empty text")
                return text
        raise KeyError(f"no active prompt for locator {locator!r}")

    @property
    def names(self) -> list[str]:
        return sorted(self._lists)

    def stats(self) -> dict:
        return {
            "records": {k: len(v) for k, v in sorted(self._records.items())},
            "records_total": sum(len(v) for v in self._records.values()),
            "lists": len(self._lists),
        }


_CATALOG: Catalog | None = None


def load() -> Catalog:
    """Build the catalog from ARCANE_DB_PATH and install it as the process-wide instance."""
    global _CATALOG
    db_path = os.environ.get("ARCANE_DB_PATH")
    if not db_path:
        raise RuntimeError("ARCANE_DB_PATH is not set")
    _CATALOG = Catalog(db_path)
    return _CATALOG


def get_catalog() -> Catalog:
    """The loaded catalog, shared by every part of the app. Call load() once at startup first."""
    if _CATALOG is None:
        raise RuntimeError("catalog not loaded — call catalog.load() at startup")
    return _CATALOG
