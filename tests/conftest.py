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
    rec("classes", "mage", {"index": "mage", "name": "Mage", "hit_die": 6,
        "saving_throws": [{"index": "int"}, {"index": "wis"}],
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-lore"}}, {"item": {"index": "skill-runes"}},
            {"item": {"index": "skill-focus"}}]}}],
        "spellcasting": {"spellcasting_ability": {"index": "int"}}})
    rec("classes", "warrior", {"index": "warrior", "name": "Warrior", "hit_die": 10,
        "saving_throws": [{"index": "str"}, {"index": "con"}],
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-brawn"}}, {"item": {"index": "skill-menace"}},
            {"item": {"index": "skill-watch"}}]}}],
        "starting_equipment_options": [
            # slot 0: pick 1 directly from a category
            {"choose": 1, "from": {"option_set_type": "equipment_category",
                                   "equipment_category": {"index": "cat-simple"}}},
            # slot 1: pick 1 of two alternatives, one being "choose from a category" (→ companion)
            {"choose": 1, "from": {"option_set_type": "options_array", "options": [
                {"option_type": "counted_reference", "count": 1, "of": {"name": "ShieldItem"}},
                {"option_type": "choice", "choice": {"choose": 1, "desc": "a martial weapon",
                    "from": {"equipment_category": {"index": "cat-martial"}}}}]}}]})
    # a PREPARED caster (no spells_known in the table → count = ability mod + level)
    rec("classes", "oracle", {"index": "oracle", "name": "Oracle", "hit_die": 8,
        "saving_throws": [{"index": "wis"}, {"index": "cha"}],
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-focus"}}, {"item": {"index": "skill-lore"}},
            {"item": {"index": "skill-watch"}}]}}],
        "spellcasting": {"spellcasting_ability": {"index": "wis"}}})
    # a martial that gets a fighting style ("fighter") and one that gets expertise ("rogue")
    rec("classes", "fighter", {"index": "fighter", "name": "Fighter", "hit_die": 10,
        "saving_throws": [{"index": "str"}, {"index": "con"}],
        "proficiencies": [{"index": "all-armor", "name": "All armor"}, {"index": "shields", "name": "Shields"},
                          {"index": "simple-weapons", "name": "Simple weapons"},
                          {"index": "martial-weapons", "name": "Martial weapons"}],
        "proficiency_choices": [{"choose": 2, "from": {"options": [
            {"item": {"index": "skill-brawn"}}, {"item": {"index": "skill-menace"}},
            {"item": {"index": "skill-watch"}}]}}]})
    rec("classes", "rogue", {"index": "rogue", "name": "Rogue", "hit_die": 8,
        "saving_throws": [{"index": "dex"}, {"index": "int"}],
        "proficiency_choices": [{"choose": 4, "from": {"options": [
            {"item": {"index": "skill-brawn"}}, {"item": {"index": "skill-menace"}},
            {"item": {"index": "skill-watch"}}, {"item": {"index": "skill-focus"}}]}}]})

    # level tables
    mage_levels = {
        1: {"cantrips_known": 3, "spells_known": 4, "spell_slots_level_1": 2},
        2: {"cantrips_known": 3, "spells_known": 5, "spell_slots_level_1": 3},
        3: {"cantrips_known": 3, "spells_known": 6, "spell_slots_level_1": 4, "spell_slots_level_2": 2},
        4: {"cantrips_known": 4, "spells_known": 7, "spell_slots_level_1": 4, "spell_slots_level_2": 3},
        5: {"cantrips_known": 4, "spells_known": 8, "spell_slots_level_1": 4, "spell_slots_level_2": 3, "spell_slots_level_3": 2},
    }
    mage_features = {1: [{"name": "Spellcasting"}], 2: [{"name": "Arcane Recovery"}]}
    for lv, sc in mage_levels.items():
        rec("levels", f"mage-{lv}", {"class": {"index": "mage"}, "level": lv, "spellcasting": sc,
                                     "features": mage_features.get(lv, [])})
    for lv in range(1, 6):
        rec("levels", f"warrior-{lv}", {"class": {"index": "warrior"}, "level": lv})
    oracle_levels = {  # prepared caster: cantrips + slots, no spells_known
        1: {"cantrips_known": 3, "spell_slots_level_1": 2},
        2: {"cantrips_known": 3, "spell_slots_level_1": 3},
        3: {"cantrips_known": 3, "spell_slots_level_1": 4, "spell_slots_level_2": 2},
        4: {"cantrips_known": 4, "spell_slots_level_1": 4, "spell_slots_level_2": 3},
        5: {"cantrips_known": 4, "spell_slots_level_1": 4, "spell_slots_level_2": 3, "spell_slots_level_3": 2},
    }
    for lv, sc in oracle_levels.items():
        rec("levels", f"oracle-{lv}", {"class": {"index": "oracle"}, "level": lv, "spellcasting": sc})
    for lv in range(1, 6):
        rec("levels", f"fighter-{lv}", {"class": {"index": "fighter"}, "level": lv})
    for lv in range(1, 7):
        rec("levels", f"rogue-{lv}", {"class": {"index": "rogue"}, "level": lv})

    # spells — cantrips + leveled (fake names); some are shared with the prepared caster (oracle)
    cantrips = [("Spark", ["mage", "oracle"]), ("Glimmer", ["mage", "oracle"]),
                ("Whisper", ["mage"]), ("Flicker", ["mage"]), ("Hush", ["mage"])]
    for i, (nm, classes) in enumerate(cantrips):
        rec("spells", f"c{i}", {"index": f"c{i}", "name": nm, "level": 0,
                                "classes": [{"index": c} for c in classes], "school": {"index": "alpha"}})
    leveled = [("Bolt", 1, ["mage", "oracle"]), ("Ward", 1, ["mage", "oracle"]), ("Mist", 1, ["mage", "oracle"]),
               ("Veil", 1, ["mage"]), ("Quake", 2, ["mage", "oracle"]), ("Gale", 2, ["mage", "oracle"]),
               ("Snare", 2, ["mage", "oracle"]), ("Ember", 3, ["mage"]), ("Frost", 3, ["mage"]), ("Surge", 3, ["mage"])]
    for i, (nm, lvl, classes) in enumerate(leveled):
        rec("spells", f"s{i}", {"index": f"s{i}", "name": nm, "level": lvl,
                                "classes": [{"index": c} for c in classes], "school": {"index": "alpha"}})
    # wizard/druid-tagged spells with magic schools — back third-caster, bonus-cantrip, and race picks
    schooled = [("Wiz Cantrip A", 0, ["wizard"], "evocation"), ("Wiz Cantrip B", 0, ["wizard"], "abjuration"),
                ("Evoke Bolt", 1, ["wizard"], "evocation"), ("Ward Sigil", 1, ["wizard"], "abjuration"),
                ("Charm Word", 1, ["wizard"], "enchantment"), ("False Image", 1, ["wizard"], "illusion"),
                ("Druid Spark", 0, ["druid"], "evocation")]
    for i, (nm, lvl, classes, school) in enumerate(schooled):
        rec("spells", f"w{i}", {"index": f"w{i}", "name": nm, "level": lvl,
                                "classes": [{"index": c} for c in classes], "school": {"index": school}})

    # skills
    for idx, nm, ab in [("lore", "Lore", "int"), ("runes", "Runes", "int"),
                        ("focus", "Focus", "wis"), ("brawn", "Brawn", "str"),
                        ("menace", "Menace", "cha"), ("watch", "Watch", "wis"),
                        ("perception", "Perception", "wis")]:   # real name → exercises passive perception
        rec("skills", idx, {"index": idx, "name": nm, "ability_score": {"index": ab}})

    # a race with an ability bonus + speed + a fixed language and a "choose 1" option
    rec("races", "human", {"index": "human", "name": "Human", "speed": 30,
                           "ability_bonuses": [{"ability_score": {"index": "int"}, "bonus": 1}],
                           "languages": [{"name": "Common"}],
                           "traits": [{"name": "Versatile"}],
                           "language_options": {"choose": 1, "from": {"option_set_type": "options_array",
                               "options": [{"item": {"name": "LangA"}}, {"item": {"name": "LangB"}}]}}})

    # a subrace: own speed override + racial_traits (subrace records use racial_traits, not traits)
    rec("subraces", "highlander", {"index": "highlander", "name": "Highlander", "speed": 35,
                                   "race": {"index": "human"},
                                   "ability_bonuses": [{"ability_score": {"index": "str"}, "bonus": 1}],
                                   "racial_traits": [{"name": "Sure-Footed"}]})

    # languages master list (for background "choose N of any language")
    for idx, nm in [("common", "Common"), ("l1", "LangA"), ("l2", "LangB"), ("l3", "LangC"), ("l4", "LangD")]:
        rec("languages", idx, {"index": idx, "name": nm})

    # background records (the model picks a name from the backgrounds list; these resolve the grants)
    rec("backgrounds", "scholar", {"index": "scholar", "name": "Scholar",
        "starting_proficiencies": [{"index": "skill-lore", "name": "Lore"}, {"index": "skill-runes", "name": "Runes"}],
        "tool_proficiencies": ["Quill"], "language_options": {"choose": 1}, "feature": {"name": "Bookish"}})
    rec("backgrounds", "outcast", {"index": "outcast", "name": "Outcast",
        "starting_proficiencies": [{"index": "skill-brawn", "name": "Brawn"}],
        "tool_proficiencies": [], "language_options": {"choose": 0}, "feature": {"name": "Hardened"}})

    # supplemental lists
    lst("abilities", ["str", "dex", "con", "int", "wis", "cha"])
    lst("standard_array", [15, 14, 13, 12, 10, 8])
    lst("ability_priority", {"mage": ["int", "con", "dex", "wis", "cha", "str"],
                             "warrior": ["str", "con", "dex", "wis", "cha", "int"],
                             "oracle": ["wis", "con", "dex", "int", "cha", "str"],
                             "fighter": ["str", "con", "dex", "wis", "cha", "int"],
                             "rogue": ["dex", "con", "int", "wis", "cha", "str"]})
    lst("backgrounds", ["Wanderer", "Scholar", "Outcast"])
    lst("alignments_display", ["Order", "Balance", "Ruin"])
    lst("known_casters", ["mage"])
    lst("prepared_casters", ["oracle"])
    lst("valid_races", ["human"])
    lst("subclass_options", {"mage": ["Evoker", "Abjurer"], "warrior": ["Champion", "Berserker"],
                             "oracle": ["Seer", "Prophet"]})
    lst("subclass_level", {"mage": 2, "warrior": 3, "oracle": 3})
    lst("subrace_bonus", {})
    lst("patron_expanded", {"shadow": {"1": ["Bolt"], "2": ["Quake"]}})
    # feature-choice lists (fighting style; expertise reads the class skill list)
    lst("fighting_styles", {"fighter": ["StyleA", "StyleB", "StyleC"]})
    lst("fighting_style_level", {"fighter": 1})
    # subclass feature-oddity value lists (synthetic)
    lst("metamagic", ["MetaA", "MetaB", "MetaC"])
    lst("invocations", ["InvA", "InvB", "InvC", "InvD"])
    lst("invocation_prereqs", {"InvA": {"requires_eldritch_blast": True}, "InvB": {"requires_pact": "boona"},
                               "InvC": {"min_level": 5}, "InvD": {"min_level": 9}})
    lst("maneuvers", ["ManA", "ManB", "ManC", "ManD"])
    lst("totem", ["TotemA", "TotemB"])
    lst("pact_boon", ["BoonA", "BoonB", "BoonC"])
    lst("draconic_ancestry", ["DracA", "DracB"])
    lst("creature_types", ["TypeA", "TypeB"])
    lst("terrain", ["TerrA", "TerrB"])
    lst("land_type", ["LandA", "LandB"])
    lst("elemental_disciplines", ["DiscA", "DiscB"])
    lst("hunters_prey", ["PreyA", "PreyB"])
    lst("defensive_tactics", ["TacA", "TacB"])
    lst("beasts", ["BeastA", "BeastB"])
    lst("knowledge_skills", ["KnowA", "KnowB", "KnowC"])
    lst("nature_skills", ["NatA", "NatB"])
    # feat / ASI
    lst("feats", ["FeatA", "FeatB", "FeatC", "FeatD"])
    lst("feat_attributes", {"FeatA": {"requires": "caster"},
                            "FeatB": {"requires": "martial", "min_ability": {"str": 13}},
                            "FeatC": {"requires": None},
                            "FeatD": {"requires": None, "requires_proficiency": "medium-armor"}})
    lst("martial_classes", ["warrior", "fighter", "rogue"])
    lst("subclass_capabilities", {"berserker": ["caster"]})   # warrior subclass that grants casting
    lst("multiclass_prereqs", {"mage": {"all": ["int"]}, "warrior": {"all": ["str", "con"]},
                               "oracle": {"all": ["wis", "cha"]}, "fighter": {"any": ["str", "dex"]},
                               "rogue": {"all": ["dex"]}})
    lst("ability_priority_subclass", {"berserker": ["con", "str", "dex", "int", "wis", "cha"]})
    lst("asi_levels", {"fighter": [4, 6, 8, 12, 14, 16, 19], "rogue": [4, 8, 10, 12, 16, 19]})
    lst("asi_default_levels", [4, 8, 12, 16, 19])
    lst("asi_label", {"str": "Strength", "dex": "Dexterity", "con": "Constitution",
                      "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"})
    # starting-equipment category → concrete items (synthetic)
    lst("category_items", {"cat-simple": ["WeaponA", "WeaponB", "WeaponC"],
                           "cat-martial": ["MartialA", "MartialB"]})
    # versioned prompts (kind "prompts"): one active per locator + a superseded one for the resolver
    rec("prompts", "sheet_sys-v1", {"index": "sheet_sys-v1", "name": "sheet_sys v1", "locator": "sheet_sys",
                                    "version": 1, "active": False, "comment": "old", "text": "OLD SHEET PROMPT"})
    rec("prompts", "sheet_sys-v2", {"index": "sheet_sys-v2", "name": "sheet_sys v2", "locator": "sheet_sys",
                                    "version": 2, "active": True, "comment": "current", "text": "TEST SYSTEM PROMPT"})
    # flavour / backstory lists
    lst("race_phys", {"Human": {"age": [16, 90], "h": [58, 78], "w": [110, 270]}})
    lst("genders", ["Male", "Female", "Nonbinary"])
    lst("eyes", ["Brown", "Blue", "Green"])
    lst("hair", ["Black", "Brown", "Auburn"])
    lst("skin_default", ["Pale", "Tan", "Dark"])
    lst("skin_overrides", {"Scaled": ["Bronze", "Silver"]})
    lst("archetypes", ["Frame them through a mundane trade.", "Bond them to a place, not a person."])
    rec("prompts", "flavour_sys-v1", {"index": "flavour_sys-v1", "name": "flavour_sys v1", "locator": "flavour_sys",
                                      "version": 1, "active": True, "comment": "current", "text": "TEST FLAVOUR PROMPT"})

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
