"""Catalog (resource layer): loads records by kind + lists by name, and the access helpers."""
import pytest


def test_records_and_record(catalog):
    assert "mage" in catalog.records("classes")
    assert catalog.record("classes", "mage")["name"] == "Mage"
    assert catalog.record("classes", "nope") is None


def test_kinds(catalog):
    assert {"classes", "levels", "spells", "skills", "races"} <= set(catalog.kinds)


def test_by_name(catalog):
    assert catalog.by_name("skills")["lore"]["name"] == "Lore"
    # cached view is stable
    assert catalog.by_name("skills") is catalog.by_name("skills")


def test_lists(catalog):
    assert catalog.get("standard_array") == [15, 14, 13, 12, 10, 8]
    assert catalog.get("missing") is None
    assert catalog.require("abilities") == ["str", "dex", "con", "int", "wis", "cha"]


def test_require_missing_raises(catalog):
    with pytest.raises(KeyError):
        catalog.require("does_not_exist")


def test_stats(catalog):
    s = catalog.stats()
    assert s["records_total"] > 0 and s["lists"] > 0
    assert "classes" in s["records"]


def test_prompt_returns_active_version(catalog):
    assert catalog.prompt("sheet_sys") == "TEST SYSTEM PROMPT"      # the active v2, not superseded v1
    assert catalog.prompt("flavour_sys") == "TEST FLAVOUR PROMPT"


def test_prompt_unknown_locator_raises(catalog):
    with pytest.raises(KeyError):
        catalog.prompt("does_not_exist")


def test_load_error_wraps_as_runtimeerror(tmp_path):
    # a missing/corrupt store must surface as a clear RuntimeError, not a raw sqlite traceback
    from app.catalog import Catalog
    bad = tmp_path / "empty.db"
    bad.write_bytes(b"")                       # opens as an empty DB → no 'entries' table
    with pytest.raises(RuntimeError, match="failed to load catalog"):
        Catalog(str(bad))


def test_prompt_active_but_empty_text_raises(tmp_path):
    # an active prompt with empty text is a misconfiguration — surface it, don't return ""
    import sqlite3
    import json as _json
    from app.catalog import Catalog
    p = tmp_path / "c.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE entries (kind TEXT, idx TEXT, name TEXT, data TEXT, PRIMARY KEY(kind, idx))")
    con.execute("CREATE TABLE catalog (name TEXT PRIMARY KEY, data TEXT)")
    con.execute("INSERT INTO entries VALUES (?,?,?,?)", ("prompts", "p1", "p1",
                _json.dumps({"locator": "sheet_sys", "active": True, "text": ""})))
    con.commit()
    con.close()
    with pytest.raises(KeyError, match="empty text"):
        Catalog(str(p)).prompt("sheet_sys")
