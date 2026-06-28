"""Shared test fixtures. Everything runs against a small SYNTHETIC catalog (fake classes/spells/
lists) built into a temp SQLite — so the tests exercise the mechanics, carry no game content, and
run anywhere without the real (local) data."""
import json
import sqlite3

import pytest

from app.catalog import Catalog


def _build_synthetic_db(path: str) -> None:
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("CREATE TABLE entries (kind TEXT, idx TEXT, name TEXT, data TEXT, PRIMARY KEY(kind, idx))")
    cur.execute("CREATE TABLE catalog (name TEXT PRIMARY KEY, data TEXT)")

    def rec(kind, idx, data):
        cur.execute("INSERT INTO entries VALUES (?,?,?,?)", (kind, idx, data.get("name", idx), json.dumps(data)))

    def lst(name, value):
        cur.execute("INSERT INTO catalog VALUES (?,?)", (name, json.dumps(value)))

    # classes — one known-caster ("mage"), one martial ("warrior")
    rec("classes", "mage", {"index": "mage", "name": "Mage",
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-lore"}}, {"item": {"index": "skill-runes"}},
            {"item": {"index": "skill-focus"}}]}}],
        "spellcasting": {"spellcasting_ability": {"index": "int"}}})
    rec("classes", "warrior", {"index": "warrior", "name": "Warrior",
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-brawn"}}, {"item": {"index": "skill-menace"}},
            {"item": {"index": "skill-watch"}}]}}]})

    # level tables
    mage_levels = {
        1: {"cantrips_known": 3, "spells_known": 4, "spell_slots_level_1": 2},
        2: {"cantrips_known": 3, "spells_known": 5, "spell_slots_level_1": 3},
        3: {"cantrips_known": 3, "spells_known": 6, "spell_slots_level_1": 4, "spell_slots_level_2": 2},
        4: {"cantrips_known": 4, "spells_known": 7, "spell_slots_level_1": 4, "spell_slots_level_2": 3},
        5: {"cantrips_known": 4, "spells_known": 8, "spell_slots_level_1": 4, "spell_slots_level_2": 3, "spell_slots_level_3": 2},
    }
    for lv, sc in mage_levels.items():
        rec("levels", f"mage-{lv}", {"class": {"index": "mage"}, "level": lv, "spellcasting": sc})
    for lv in range(1, 6):
        rec("levels", f"warrior-{lv}", {"class": {"index": "warrior"}, "level": lv})

    # spells — 5 cantrips + leveled, all on the mage list (fake names)
    for i, nm in enumerate(["Spark", "Glimmer", "Whisper", "Flicker", "Hush"]):
        rec("spells", f"c{i}", {"index": f"c{i}", "name": nm, "level": 0,
                                "classes": [{"index": "mage"}], "school": {"index": "alpha"}})
    for i, (nm, lvl) in enumerate([("Bolt", 1), ("Ward", 1), ("Mist", 1), ("Veil", 1),
                                   ("Quake", 2), ("Gale", 2), ("Snare", 2),
                                   ("Ember", 3), ("Frost", 3), ("Surge", 3)]):
        rec("spells", f"s{i}", {"index": f"s{i}", "name": nm, "level": lvl,
                                "classes": [{"index": "mage"}], "school": {"index": "alpha"}})

    # skills
    for idx, nm, ab in [("lore", "Lore", "int"), ("runes", "Runes", "int"),
                        ("focus", "Focus", "wis"), ("brawn", "Brawn", "str"),
                        ("menace", "Menace", "cha"), ("watch", "Watch", "wis")]:
        rec("skills", idx, {"index": idx, "name": nm, "ability_score": {"index": ab}})

    # a race with an ability bonus
    rec("races", "human", {"index": "human", "name": "Human",
                           "ability_bonuses": [{"ability_score": {"index": "int"}, "bonus": 1}]})

    # supplemental lists
    lst("abilities", ["str", "dex", "con", "int", "wis", "cha"])
    lst("standard_array", [15, 14, 13, 12, 10, 8])
    lst("ability_priority", {"mage": ["int", "con", "dex", "wis", "cha", "str"],
                             "warrior": ["str", "con", "dex", "wis", "cha", "int"]})
    lst("backgrounds", ["Wanderer", "Scholar", "Outcast"])
    lst("alignments_display", ["Order", "Balance", "Ruin"])
    lst("known_casters", ["mage"])
    lst("prepared_casters", [])
    lst("valid_races", ["human"])
    lst("subclass_options", {"mage": ["Evoker", "Abjurer"], "warrior": ["Champion", "Berserker"]})
    lst("subclass_level", {"mage": 2, "warrior": 3})
    lst("subrace_bonus", {})
    lst("patron_expanded", {})
    lst("prompt_sheet_sys", "TEST SYSTEM PROMPT")

    con.commit()
    con.close()


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> str:
    p = tmp_path / "catalog.db"
    _build_synthetic_db(str(p))
    monkeypatch.setenv("ARCANE_DB_PATH", str(p))
    monkeypatch.setenv("OLLAMA_URL", "http://test")
    monkeypatch.setenv("MODEL", "test-model")
    return str(p)


@pytest.fixture
def catalog(db_path) -> Catalog:
    return Catalog(db_path)
