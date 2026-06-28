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
