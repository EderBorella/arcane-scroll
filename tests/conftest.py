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
        "proficiencies": [{"index": "foils", "name": "Foils"}],
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

    # armour equipment records (for armour-based AC detection)
    rec("equipment", "chain-mail", {"index": "chain-mail", "name": "Chain Mail", "armor_category": "Heavy",
                                    "armor_class": {"base": 16, "dex_bonus": False}})
    rec("equipment", "leather-armor", {"index": "leather-armor", "name": "Leather Armor", "armor_category": "Light",
                                       "armor_class": {"base": 11, "dex_bonus": True}})
    rec("equipment", "half-plate", {"index": "half-plate", "name": "Half Plate Armor", "armor_category": "Medium",
                                    "armor_class": {"base": 15, "dex_bonus": True, "max_bonus": 2}})
    # name-subset trap: "Plate Armor" ⊂ "Half Plate Armor", "Leather Armor" ⊂ "Studded Leather Armor"
    rec("equipment", "plate-armor", {"index": "plate-armor", "name": "Plate Armor", "armor_category": "Heavy",
                                     "armor_class": {"base": 18, "dex_bonus": False}})
    rec("equipment", "studded-leather", {"index": "studded-leather", "name": "Studded Leather Armor",
                                         "armor_category": "Light", "armor_class": {"base": 12, "dex_bonus": True}})
    rec("equipment", "shield", {"index": "shield", "name": "Shield", "armor_category": "Shield",
                                "armor_class": {"base": 2, "dex_bonus": False}})

    # weapon equipment records (for attack rows) — category / range / damage / properties like the API
    rec("equipment", "club", {"index": "club", "name": "Club", "equipment_category": {"index": "weapon"},
        "weapon_category": "Simple", "weapon_range": "Melee",
        "damage": {"damage_dice": "1d4", "damage_type": {"name": "Bludgeoning"}}, "properties": []})
    rec("equipment", "pike", {"index": "pike", "name": "Pike", "equipment_category": {"index": "weapon"},
        "weapon_category": "Simple", "weapon_range": "Melee",
        "damage": {"damage_dice": "1d6", "damage_type": {"name": "Piercing"}},
        "two_handed_damage": {"damage_dice": "1d8", "damage_type": {"name": "Piercing"}},
        "properties": [{"index": "versatile", "name": "Versatile"}]})
    rec("equipment", "blade", {"index": "blade", "name": "Blade", "equipment_category": {"index": "weapon"},
        "weapon_category": "Martial", "weapon_range": "Melee",
        "damage": {"damage_dice": "1d8", "damage_type": {"name": "Slashing"}}, "properties": []})
    rec("equipment", "foil", {"index": "foil", "name": "Foil", "equipment_category": {"index": "weapon"},
        "weapon_category": "Martial", "weapon_range": "Melee",
        "damage": {"damage_dice": "1d8", "damage_type": {"name": "Piercing"}},
        "properties": [{"index": "finesse", "name": "Finesse"}]})
    rec("equipment", "maul", {"index": "maul", "name": "Maul", "equipment_category": {"index": "weapon"},
        "weapon_category": "Martial", "weapon_range": "Melee",
        "damage": {"damage_dice": "2d6", "damage_type": {"name": "Bludgeoning"}},
        "properties": [{"index": "two-handed", "name": "Two-Handed"}]})
    rec("equipment", "bow", {"index": "bow", "name": "Bow", "equipment_category": {"index": "weapon"},
        "weapon_category": "Martial", "weapon_range": "Ranged",
        "damage": {"damage_dice": "1d8", "damage_type": {"name": "Piercing"}},
        "properties": [{"index": "ammunition", "name": "Ammunition"}, {"index": "two-handed", "name": "Two-Handed"}]})

    # background records (the model picks a name from the backgrounds list; these resolve the grants)
    rec("backgrounds", "scholar", {"index": "scholar", "name": "Scholar",
        "starting_proficiencies": [{"index": "skill-lore", "name": "Lore"}, {"index": "skill-runes", "name": "Runes"}],
        "tool_proficiencies": ["Quill"], "language_options": {"choose": 1}, "feature": {"name": "Bookish"},
        "starting_gold": {"quantity": 15, "unit": "gp"}})
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
    lst("starting_wealth", {"warrior": {"dice": "2d4", "x": 10}, "mage": {"dice": "4d4", "x": 10}})
    lst("alignments_display", ["Order", "Balance", "Ruin"])
    lst("known_casters", ["mage"])
    lst("prepared_casters", ["oracle"])
    lst("caster_progression", {"mage": "full", "oracle": "full"})   # synthetic full casters
    lst("unarmoured_defence", {"barbarian": "con", "monk": "wis"})
    lst("third_caster_subclasses", ["Arcane Trickster", "Eldritch Knight"])
    lst("valid_races", ["Human"])          # display names (canonical form parse resolves to)
    lst("subclass_options", {"mage": ["Evoker", "Abjurer"], "warrior": ["Champion", "Berserker"],
                             "oracle": ["Seer", "Prophet"]})
    lst("subclass_level", {"mage": 2, "warrior": 3, "oracle": 3})
    lst("subrace_bonus", {})
    lst("patron_expanded", {"shadow": {"1": ["Bolt"], "2": ["Quake"]}})
    lst("subclass_spells", {"seer": {"1": ["Bolt"], "3": ["Quake", "Gale"]}})   # always-prepared grants
    lst("land_spells", {"landa": {"1": ["Bolt"], "3": ["Quake"]}})              # Circle of the Land, by land type
    # feature-choice lists (fighting style; expertise reads the class skill list)
    lst("fighting_styles", {"fighter": ["StyleA", "StyleB", "StyleC"]})
    lst("fighting_style_level", {"fighter": 1})
    lst("fighting_style_equipment", {"Dueling": {"max_weapons": 1, "exclude_props": ["two-handed"]},
                                     "Two-Weapon Fighting": {"min_weapons": 2, "exclude_props": ["two-handed"]}})
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
    # class->equipment relation (seed-derived in prod; hand-mirrors warrior's options here). slots()
    # reads THIS, not the raw class record.
    lst("class_equipment", {"warrior": {"fixed": [], "slots": [
        {"field": "equipment_0", "choose": 1, "category": "cat-simple"},
        {"field": "equipment_1", "choose": 1, "alternatives": [
            {"label": "ShieldItem", "items": [{"item": "ShieldItem", "qty": 1}], "pick": None},
            {"label": "a martial weapon", "items": [], "pick": {"category": "cat-martial", "n": 1}}]}]}})
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
    rec("prompts", "equip_sys-v1", {"index": "equip_sys-v1", "name": "equip_sys v1", "locator": "equip_sys",
                                    "version": 1, "active": True, "comment": "current", "text": "TEST EQUIP PROMPT"})

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


def _build_rules_db(path: str) -> None:
    con = sqlite3.connect(path)   # tests/conftest.py already imports sqlite3 and pytest
    cur = con.cursor()
    cur.execute("CREATE TABLE class (id TEXT PRIMARY KEY, name TEXT, hit_die_faces INT, "
                "subclass_level INT, caster_progression TEXT, primary_mode TEXT, "
                "skill_choose_n INT, skill_from_any INT, description TEXT)")
    cur.execute("CREATE TABLE subclass (id TEXT PRIMARY KEY, class_id TEXT, name TEXT, is_caster INT, description TEXT)")
    cur.execute("CREATE TABLE species (id TEXT PRIMARY KEY, name TEXT, creature_type_id TEXT, base_walk_speed INT, description TEXT)")
    cur.execute("CREATE TABLE background (id TEXT PRIMARY KEY, name TEXT, feat_id TEXT, feat_choice INT, tool_id TEXT, tool_category_id TEXT, description TEXT)")
    cur.execute("CREATE TABLE lineage (id TEXT PRIMARY KEY, name TEXT, description TEXT)")
    cur.execute("CREATE TABLE size (id TEXT PRIMARY KEY, name TEXT, ordinal INT, space_ft REAL)")
    cur.execute("CREATE TABLE creature_type (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE xp_level (level INT PRIMARY KEY, xp_min INT)")
    # abilities domain: ability identity + background boost lists + class saves + ASI/HP grant spine
    cur.execute("CREATE TABLE ability (id TEXT PRIMARY KEY, name TEXT, abbrev TEXT)")
    cur.execute("CREATE TABLE background_ability (background_id TEXT, ability_id TEXT, ordinal INT)")
    cur.execute("CREATE TABLE class_saving_throw (class_id TEXT, ability_id TEXT)")
    cur.execute("CREATE TABLE point_buy_cost (score INT PRIMARY KEY, cost INT)")
    cur.execute("CREATE TABLE rules_constant (id TEXT PRIMARY KEY, value_int INTEGER, note TEXT)")
    cur.execute("CREATE TABLE grant_ability_increase (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, points INT, max_per_ability INT, cap INT, from_any INT, condition_kind TEXT)")
    cur.execute("CREATE TABLE grant_ability_set (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, ability_id TEXT, score INT, mode TEXT, condition_kind TEXT)")
    cur.execute("CREATE TABLE grant_hp (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, flat INT, per_level INT, condition_kind TEXT)")
    cur.execute("INSERT INTO class VALUES ('class-a','Class A',8,3,'full','all',2,0,'')")
    cur.execute("INSERT INTO class VALUES ('class-b','Class B',10,3,'none','any',2,0,'')")
    cur.execute("INSERT INTO subclass VALUES ('sub-a','class-a','Sub A',1,'')")
    cur.execute("INSERT INTO subclass VALUES ('sub-b','class-b','Sub B',0,'')")
    # sub-skills / sub-save: class-a subclasses used by the subclass-grant fixtures below
    # (grant_proficiency rows inserted once that table exists, in the proficiencies/feats sections)
    cur.execute("INSERT INTO subclass VALUES ('sub-skills','class-a','Sub Skills',0,'')")
    cur.execute("INSERT INTO subclass VALUES ('sub-save','class-a','Sub Save',0,'')")
    # sub-save-late: a class-a subclass whose save grant only kicks in at class level 7
    # (a level-gated subclass save grant -- gained_at_level gating fix's fixture)
    cur.execute("INSERT INTO subclass VALUES ('sub-save-late','class-a','Sub Save Late',0,'')")
    cur.execute("INSERT INTO creature_type VALUES ('type-a','Type A')")
    cur.execute("INSERT INTO creature_type VALUES ('type-b','Type B')")
    cur.execute("INSERT INTO species VALUES ('species-a','Species A','type-a',30,'')")
    cur.execute("INSERT INTO background VALUES ('bg-a','Background A','feat-origin',0,NULL,NULL,'')")
    # bg-b: a background with no origin feat grant (feat_id NULL) -- the negative case for the
    # background.feat_id-sourced origin budget
    cur.execute("INSERT INTO background VALUES ('bg-b','Background B',NULL,0,NULL,NULL,'')")
    cur.execute("INSERT INTO size VALUES ('size-a','Size A',3,5.0)")
    for lvl, xp in [(1, 0), (2, 300), (3, 900), (4, 2700), (5, 6500)]:
        cur.execute("INSERT INTO xp_level VALUES (?,?)", (lvl, xp))
    for i in range(1, 7):
        cur.execute("INSERT INTO ability VALUES (?,?,?)", (f"a{i}", f"Ability {i}", f"x{i}"))
    # Ability whose full DB id ('wisdom') is referenced by the scaling-formula variable
    # owner_wisdom_modifier and whose short abbrev ('wis') is how CORE keys it —
    # exercises the abbrev bridge in the companion owner-context resolver.
    cur.execute("INSERT INTO ability VALUES ('wisdom','Wisdom','wis')")
    for aid, ordinal in [("a1", 1), ("a2", 2), ("a3", 3)]:
        cur.execute("INSERT INTO background_ability VALUES ('bg-a',?,?)", (aid, ordinal))
    for aid in ("a1", "a2"):
        cur.execute("INSERT INTO class_saving_throw VALUES ('class-a',?)", (aid,))
    for score, cost in [(8, 0), (9, 1), (10, 2), (11, 3), (12, 4), (13, 5), (14, 7), (15, 9)]:
        cur.execute("INSERT INTO point_buy_cost VALUES (?,?)", (score, cost))
    cur.execute("INSERT INTO rules_constant VALUES ('point-buy-budget',27,'')")
    cur.execute("INSERT INTO grant_ability_increase VALUES "
                "('gai-asi','feat','ability-score-improvement',NULL,2,2,20,1,NULL)")

    # proficiencies domain: skills catalog + class/background skill pools + skill/expertise grants
    cur.execute("CREATE TABLE skill (id TEXT PRIMARY KEY, name TEXT, ability_id TEXT)")
    cur.execute("CREATE TABLE class_skill_option (class_id TEXT, skill_id TEXT)")
    cur.execute("CREATE TABLE background_skill (background_id TEXT, skill_id TEXT)")
    cur.execute("CREATE TABLE grant_proficiency (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, target_kind TEXT, mode TEXT, from_any INT, choose_n INT, "
                "multiclass_only INT, condition_kind TEXT)")
    cur.execute("CREATE TABLE grant_proficiency_value (grant_id TEXT, target_id TEXT)")
    # children_of() fans out over the whole grant_proficiency child list (access/primitives.py's
    # GRANT_TABLES); these two are unused by the skills fixture but must exist for the query.
    cur.execute("CREATE TABLE grant_proficiency_category (grant_id TEXT, tool_category_id TEXT)")
    cur.execute("CREATE TABLE grant_proficiency_weapon_filter (grant_id TEXT, property_id TEXT)")
    cur.execute("CREATE TABLE grant_expertise (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, choose_n INT, mode TEXT, skill_id TEXT)")
    cur.execute("CREATE TABLE grant_expertise_value (grant_id TEXT, skill_id TEXT)")
    for i in range(1, 8):
        cur.execute("INSERT INTO skill VALUES (?,?,?)", (f"sk{i}", f"Sk{i}", "a1"))
    # class-a (skill_choose_n=2, skill_from_any=0): choose 2 from {sk1,sk2,sk3}
    for sid in ("sk1", "sk2", "sk3"):
        cur.execute("INSERT INTO class_skill_option VALUES ('class-a',?)", (sid,))
    # bg-a: 1 fixed background skill
    cur.execute("INSERT INTO background_skill VALUES ('bg-a','sk4')")
    # species-a grants a fixed skill proficiency (sk5) -- exercises grant-sourced skills
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-species-a-skill','species','species-a',NULL,'skill','fixed',0,NULL,0,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-species-a-skill','sk5')")
    # class-b grants a reduced multiclass-only skill (sk6) -- what a secondary (non-first) class
    # confers, per grant_proficiency.multiclass_only=1
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-class-b-multiclass-skill','class','class-b',NULL,'skill','fixed',0,NULL,1,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-class-b-multiclass-skill','sk6')")
    # class-r (a rogue-analogue secondary class): its multiclass-only skill grant is CHOOSE-mode
    # with choose_n=1 and NO explicit value pool -- mirrors the real DB fact for rogue's multiclass
    # table row (id gpr-0382: owner_kind='class', owner_id='rogue', target_kind='skill',
    # mode='choose', choose_n=1, from_any=0, multiclass_only=1, zero grant_proficiency_value rows).
    # The real schema resolves the pool via a from_class_list column this synthetic schema doesn't
    # model, so -- as with the existing any-flag fallback below -- an empty-pool choose grant here
    # widens legality to any skill; the point of this fixture is the previously-uncredited choose_n
    # budget cost, not the pool-resolution mechanism (out of scope for this fix).
    cur.execute("INSERT INTO class VALUES ('class-r','Class R',8,3,'none','all',4,0,'')")
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-class-r-multiclass-skill','class','class-r',NULL,'skill','choose',0,1,1,NULL)")
    # sub-skills (class-a's subclass): a College-of-Lore-style grant -- choose 3 skills of your
    # choice (mode='choose', from_any=1, choose_n=3, no restricted value pool) via the
    # owner_kind='subclass' proficiency grant spine -- the subclass-skill-grant fix's fixture.
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-subclass-skills','subclass','sub-skills',NULL,'skill','choose',1,3,0,NULL)")
    # class-a grants 1 expertise pick at level 1, from already-proficient skills (unrestricted pool)
    cur.execute("INSERT INTO grant_expertise VALUES "
                "('gex-a','class','class-a',1,1,'choose_from_proficient',NULL)")
    # ... and a second expertise pick at level 6 (mirrors e.g. rogue L1->2, L6->2 -- two separate
    # per-level grants summing over a class's own levels); no existing test uses class-a above
    # level 3, so this is additive-only for the multiclass-expertise-budget fix
    cur.execute("INSERT INTO grant_expertise VALUES "
                "('gex-a6','class','class-a',6,1,'choose_from_proficient',NULL)")

    # armor/weapon/tool proficiency spine (F05-T19): catalog tables + grant rows
    cur.execute("CREATE TABLE armor_category (id TEXT PRIMARY KEY, name TEXT, don_minutes REAL, doff_minutes REAL)")
    cur.execute("CREATE TABLE weapon_tier (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE tool_category (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE tool (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE tool_category_item (tool_category_id TEXT, tool_id TEXT)")

    for aid, aname in [("light-armor","Light Armor"),("medium-armor","Medium Armor"),("heavy-armor","Heavy Armor"),("shield","Shield")]:
        cur.execute("INSERT INTO armor_category VALUES (?,?,1,1)", (aid, aname))
    for wid, wname in [("simple","Simple"),("martial","Martial")]:
        cur.execute("INSERT INTO weapon_tier VALUES (?,?)", (wid, wname))
    cur.execute("INSERT INTO tool_category VALUES ('artisan-s-tools',\"Artisan's Tools\")")

    cur.execute("INSERT INTO tool VALUES ('herbalism-kit','Herbalism Kit')")
    cur.execute("INSERT INTO tool VALUES ('smith-s-tools',\"Smith's Tools\")")

    # class-a: light+medium armor + simple weapons (multiclass_only=0 --> full when primary)
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,from_any,choose_n,multiclass_only) VALUES ('gpr-armor','class','class-a',NULL,'armor_category','fixed',0,NULL,0)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-armor','light-armor')")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-armor','medium-armor')")
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,from_any,choose_n,multiclass_only) VALUES ('gpr-weapon','class','class-a',NULL,'weapon_tier','fixed',0,NULL,0)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-weapon','simple')")

    # background grants 1 specific tool
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,from_any,choose_n,multiclass_only) VALUES ('gpr-bg-tool','background','bg-a',NULL,'tool','fixed',0,NULL,0)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-bg-tool','herbalism-kit')")

    # subclass sub-a grants shield at level 3
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,from_any,choose_n,multiclass_only) VALUES ('gpr-sub-shield','subclass','sub-a',3,'armor_category','fixed',0,NULL,0)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-sub-shield','shield')")

    # class-b multiclass_only weapon grant (martial, only when taken as secondary class)
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,from_any,choose_n,multiclass_only) VALUES ('gpr-classb-weapon','class','class-b',NULL,'weapon_tier','fixed',0,NULL,1)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gpr-classb-weapon','martial')")

    # feats domain: feat catalog, prerequisite rows, ASI/Epic-Boon slot spine (class_feature), and
    # the origin-feat grant spine (grant_feat)
    cur.execute("CREATE TABLE feat (id TEXT PRIMARY KEY, name TEXT, category TEXT, repeatable INT)")
    cur.execute("CREATE TABLE feat_prereq (id TEXT PRIMARY KEY, feat_id TEXT, any_of_group INT, kind TEXT, "
                "min_level INT, ability_id TEXT, min_score INT, armor_category_id TEXT, note TEXT)")
    cur.execute("CREATE TABLE class_feature (id TEXT PRIMARY KEY, class_id TEXT, level INT, name TEXT)")
    cur.execute("CREATE TABLE grant_feat (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, condition_kind TEXT, choose_n INT, from_category TEXT)")
    for row in [
        ("feat-gen", "Feat Gen", "general", 0),
        ("feat-rep", "Feat Rep", "general", 1),
        ("feat-origin", "Feat Origin", "origin", 0),
        ("feat-pre", "Feat Pre", "general", 0),
        ("feat-save", "Feat Save", "general", 0),
    ]:
        cur.execute("INSERT INTO feat VALUES (?,?,?,?)", row)
    # feat-save (e.g. Resilient) grants saving-throw proficiency in ability a3 via the proficiency
    # grant spine (target_kind='saving_throw') -- the saving-throws domain's feat-granted-save fix
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-featsave','feat','feat-save',NULL,'saving_throw','fixed',0,NULL,0,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-featsave','a3')")
    # sub-save (class-a's subclass) grants saving-throw proficiency in a3 via the same proficiency
    # grant spine, owner_kind='subclass' -- a subclass-granted (always-on) save; the
    # subclass-granted-save fix's fixture.
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-subclass-save','subclass','sub-save',NULL,'saving_throw','fixed',0,NULL,0,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-subclass-save','a3')")
    # sub-save-late grants the same a3 save proficiency, but only from class level 7 onward
    # (gained_at_level=7) -- the gained_at_level gating fix's fixture (a level-gated subclass save
    # grant is a real DB pattern granted at a specific level, not level 1).
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-subclass-save-late','subclass','sub-save-late',7,'saving_throw','fixed',0,NULL,0,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-subclass-save-late','a3')")
    # class-b's OWN level-gated feature grants a3 saving-throw proficiency from class level 7 onward
    # (owner_kind='class', gained_at_level=7) -- a high-level class feature that grants extra saves,
    # like a class's L14/L15 save feature. The saving-throws check must consume it for EVERY class
    # entry (not just the first) and gate it by that entry's level.
    cur.execute("INSERT INTO grant_proficiency VALUES "
                "('gp-class-save-late','class','class-b',7,'saving_throw','fixed',0,NULL,0,NULL)")
    cur.execute("INSERT INTO grant_proficiency_value VALUES ('gp-class-save-late','a3')")
    # feat-pre needs total_level>=4 (group 1) AND ability a1>=13 (group 2) -- AND across groups,
    # OR within a group (single row per group here, so each group's one row must hold)
    cur.execute("INSERT INTO feat_prereq VALUES "
                "('fpx1','feat-pre',1,'level',4,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO feat_prereq VALUES "
                "('fpx2','feat-pre',2,'ability',NULL,'a1',13,NULL,NULL)")
    # class-a's ASI/Epic-Boon slots: one at level 4, one at level 8 (two distinct slots by level 8 --
    # needed so a repeatable feat can legitimately be taken twice in the domain tests)
    cur.execute("INSERT INTO class_feature VALUES ('cf-asi4','class-a',4,'Ability Score Improvement')")
    cur.execute("INSERT INTO class_feature VALUES ('cf-asi8','class-a',8,'Ability Score Improvement')")
    # (origin-feat budget now comes from background.feat_id, set above for bg-a -- NOT grant_feat;
    # the grant_feat spine is still used for species-granted origin feats, see feats-check tests)

    # movement domain: movement_mode catalog + grant_speed spine (F05) + class_resource speed bonuses
    cur.execute("CREATE TABLE movement_mode (id TEXT PRIMARY KEY, name TEXT, hover_capable INT)")
    for mid, mname in [("walk", "Walk"), ("fly", "Fly"), ("swim", "Swim"), ("climb", "Climb")]:
        cur.execute("INSERT INTO movement_mode VALUES (?,?,0)", (mid, mname))
    cur.execute("CREATE TABLE grant_speed (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, movement_mode_id TEXT, feet INTEGER, "
                "equals_walk INTEGER DEFAULT 0, sets_total INTEGER DEFAULT 0, additive INTEGER DEFAULT 0, "
                "note TEXT, condition_kind TEXT)")
    cur.execute("INSERT INTO grant_speed VALUES "
                "('gsd-feat','feat','feat-gen',NULL,'walk',10,0,0,1,NULL,NULL)")
    cur.execute("INSERT INTO grant_speed VALUES "
                "('gsd-sub-swim','subclass','sub-a',3,'swim',NULL,1,0,0,NULL,NULL)")
    cur.execute("INSERT INTO grant_speed VALUES "
                "('gsd-feat-fly','feat','feat-rep',NULL,'fly',NULL,1,0,0,NULL,NULL)")

    cur.execute("INSERT INTO feat VALUES ('feat-over','Feat Over','general',0)")
    cur.execute("INSERT INTO grant_speed VALUES "
                "('gsd-feat-over','feat','feat-over',NULL,'climb',20,0,1,0,NULL,NULL)")

    cur.execute("CREATE TABLE class_resource (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, name TEXT)")
    cur.execute("CREATE TABLE class_resource_level (resource_id TEXT, level INTEGER, count INTEGER, "
                "die_count INTEGER, die_faces INTEGER, bonus INTEGER)")
    cur.execute("INSERT INTO class_resource VALUES ('unarmored-movement','class','class-a','Unarmored Movement')")
    cur.execute("INSERT INTO class_resource_level VALUES ('unarmored-movement',2,NULL,NULL,NULL,10)")
    cur.execute("INSERT INTO class_resource_level VALUES ('unarmored-movement',6,NULL,NULL,NULL,15)")

    # recharge_cadence — referenced by grant_spell.recharge_id (e.g. short-rest)
    cur.execute("CREATE TABLE recharge_cadence (id TEXT PRIMARY KEY, name TEXT)")

    # class_option — needed for grant_spell owner_kind='class_option' (Pact of the Tome analog)
    cur.execute("CREATE TABLE class_option (id TEXT PRIMARY KEY, catalog TEXT, owner_kind TEXT, "
                "owner_id TEXT, name TEXT, resource_kind TEXT, resource_id TEXT, resource_cost INTEGER, "
                "repeatable INTEGER DEFAULT 0, description TEXT)")

    # spellcasting domain: slot tables (single-class/multiclass/pact), cantrip+prepared counts,
    # third-caster subclass slots, spell catalog + class-list membership, and the always-granted
    # spell spine (grant_spell -> grant_spell_fixed; grant_spell_choice(_value) unused here but must
    # exist, same idiom as the proficiency-grant child tables above)
    cur.execute("CREATE TABLE class_spell_slot (class_id TEXT, class_level INT, slot_level INT, slot_count INT)")
    cur.execute("CREATE TABLE multiclass_slot (caster_level INT, slot_level INT, slot_count INT)")
    cur.execute("CREATE TABLE pact_slot (class_id TEXT, class_level INT, slot_count INT, slot_level INT)")
    cur.execute("CREATE TABLE class_cantrips_prepared (class_id TEXT, level INT, cantrips_known INT, prepared_spells INT)")
    cur.execute("CREATE TABLE subclass_spellcasting (subclass_id TEXT PRIMARY KEY, "
                "ability_id TEXT, spell_list_class_id TEXT)")
    cur.execute("CREATE TABLE subclass_spell_slot (subclass_id TEXT, class_level INT, slot_level INT, slot_count INT)")
    cur.execute("CREATE TABLE subclass_cantrips_prepared (subclass_id TEXT, class_level INT, "
                "cantrips_known INT, prepared_spells INT)")
    cur.execute("CREATE TABLE spell (id TEXT PRIMARY KEY, name TEXT, level INT, is_ritual INT)")
    cur.execute("CREATE TABLE spell_class (spell_id TEXT, class_id TEXT)")
    cur.execute("CREATE TABLE grant_spell (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, gained_at_level INT)")
    cur.execute("CREATE TABLE grant_spell_fixed (grant_id TEXT, spell_id TEXT)")
    cur.execute("CREATE TABLE grant_spell_choice (grant_id TEXT, choose_n INT, "
                "choose_n_kind TEXT DEFAULT 'int', from_kind TEXT, "
                "spell_level_min INT, spell_level_max INT, class_list_id TEXT, "
                "recurrence TEXT DEFAULT 'once')")
    cur.execute("CREATE TABLE grant_spell_choice_value (grant_id TEXT, value_id TEXT)")

    # class-a (already 'full') L3: 2 cantrips known, 3 prepared; slots {1:4, 2:2}
    cur.execute("INSERT INTO class_cantrips_prepared VALUES ('class-a',3,2,3)")
    cur.execute("INSERT INTO class_spell_slot VALUES ('class-a',3,1,4)")
    cur.execute("INSERT INTO class_spell_slot VALUES ('class-a',3,2,2)")
    # combined multiclass caster level 4 -> slots {1:4, 2:3} (distinct from class-a's own L3 table,
    # so a test can tell the multiclass path was actually used)
    cur.execute("INSERT INTO multiclass_slot VALUES (4,1,4)")
    cur.execute("INSERT INTO multiclass_slot VALUES (4,2,3)")
    cur.execute("INSERT INTO multiclass_slot VALUES (1,1,2)")
    # sub-b (class-b's subclass) is a third-caster subclass -- combined with class-a L3 (full, +3)
    # it contributes floor(3/3)=1, reaching combined caster level 4. Its own spell_list_class_id is
    # unused by the multiclass-slots tests, so it's left NULL here.
    cur.execute("INSERT INTO subclass_spellcasting VALUES ('sub-b',NULL,NULL)")
    # class-m: a non-caster class (like Fighter/Rogue) whose subclass sub-ek is a third-caster that
    # casts from class-a's list (like Eldritch Knight casting from wizard's list) -- the
    # spell-not-on-list false-positive fix's fixture
    cur.execute("INSERT INTO class VALUES ('class-m','Class M',10,3,'none','all',2,0,'')")
    cur.execute("INSERT INTO subclass VALUES ('sub-ek','class-m','Sub EK',1,'')")
    cur.execute("INSERT INTO subclass_spellcasting VALUES ('sub-ek','a1','class-a')")
    cur.execute("INSERT INTO subclass_cantrips_prepared VALUES ('sub-ek',3,2,3)")
    cur.execute("INSERT INTO subclass_spell_slot VALUES ('sub-ek',3,1,2)")
    cur.execute("INSERT INTO subclass_spell_slot VALUES ('sub-ek',4,1,3)")
    # a pact caster class + its pact slot table (2 slots at slot-level 1, for class-p level 2)
    cur.execute("INSERT INTO class VALUES ('class-p','Class P',8,3,'pact','all',2,0,'')")
    cur.execute("INSERT INTO pact_slot VALUES ('class-p',2,2,1)")
    # spells: sp1/sp2 cantrips, sp3/sp4 leveled; sp1-sp3 on class-a's list, sp4 deliberately off it
    for sid, name, level in [("sp1", "Sp1", 0), ("sp2", "Sp2", 0), ("sp3", "Sp3", 1), ("sp4", "Sp4", 1)]:
        cur.execute("INSERT INTO spell VALUES (?,?,?,0)", (sid, name, level))
    for sid in ("sp1", "sp2", "sp3"):
        cur.execute("INSERT INTO spell_class VALUES (?,'class-a')", (sid,))
    # species-a always grants sp4 (legal even though it's off class-a's list)
    cur.execute("INSERT INTO grant_spell VALUES ('gsp-species-a','species','species-a',NULL)")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-species-a','sp4')")
    # sp5 is on class-b's list only (not class-a's) -- the Magical-Secrets-style widening fixture
    cur.execute("INSERT INTO spell VALUES ('sp5','Sp5',1,0)")
    cur.execute("INSERT INTO spell_class VALUES ('sp5','class-b')")
    # class-a's Magical-Secrets-style widening grant, gained at level 10 -- mirrors the real Bard
    # L10 row (id l10-gsp-0010): grant_spell(owner_kind='class', owner_id='bard', gained_at_level=10)
    # + grant_spell_choice(from_kind='class_list') + grant_spell_choice_value = {bard, cleric, druid,
    # wizard}. Here it widens class-a's legal list to include class-b's list once the character has
    # reached level 10 in class-a, so a prepared sp5 (class-b only) becomes legal from that level on.
    cur.execute("INSERT INTO grant_spell VALUES ('gsp-classa-widen','class','class-a',10)")
    cur.execute("INSERT INTO grant_spell_choice (grant_id,choose_n,from_kind) VALUES ('gsp-classa-widen',NULL,'class_list')")
    cur.execute("INSERT INTO grant_spell_choice_value VALUES ('gsp-classa-widen','class-a')")
    cur.execute("INSERT INTO grant_spell_choice_value VALUES ('gsp-classa-widen','class-b')")

    # senses domain: sense catalog + grant_sense spine (F05-T23 max-not-sum rule)
    cur.execute("CREATE TABLE sense (id TEXT PRIMARY KEY, name TEXT, description TEXT)")
    cur.execute("CREATE TABLE grant_sense (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, sense_id TEXT, range_ft INTEGER, "
                "extends_existing INTEGER NOT NULL DEFAULT 0, note TEXT, condition_kind TEXT)")
    for sid, sname in [("darkvision", "Darkvision"), ("blindsight", "Blindsight")]:
        cur.execute("INSERT INTO sense VALUES (?,?,?)", (sid, sname, ""))
    # species-a grants darkvision 60 (non-extending base)
    cur.execute("INSERT INTO grant_sense VALUES "
                "('gs-species-a','species','species-a',NULL,'darkvision',60,0,NULL,NULL)")
    # subclass sub-a grants darkvision 120 (also non-extending — should be max, not sum)
    cur.execute("INSERT INTO grant_sense VALUES "
                "('gs-sub-a','subclass','sub-a',3,'darkvision',120,0,NULL,NULL)")
    # a feat that extends existing darkvision by 30
    cur.execute("INSERT INTO grant_sense VALUES "
                "('gs-feat-extend','feat','feat-gen',NULL,'darkvision',30,1,'if you already have it',NULL)")
    # a feat that grants blindsight 10
    cur.execute("INSERT INTO grant_sense VALUES "
                "('gs-feat-blind','feat','feat-rep',NULL,'blindsight',10,0,NULL,NULL)")

    # defenses domain: damage types, conditions, resistance/condition/save-advantage grants
    cur.execute("CREATE TABLE damage_type (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE condition (id TEXT PRIMARY KEY, name TEXT)")
    for did, dname in [("fire","Fire"),("cold","Cold"),("poison","Poison")]:
        cur.execute("INSERT INTO damage_type VALUES (?,?)", (did, dname))
    for cid, cname in [("charmed","Charmed"),("frightened","Frightened"),("poisoned","Poisoned"),
                        ("blinded","Blinded"),("incapacitated","Incapacitated"),
                        ("prone","Prone"),("unconscious","Unconscious")]:
        cur.execute("INSERT INTO condition VALUES (?,?)", (cid, cname))

    cur.execute("CREATE TABLE grant_resistance (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, damage_type_id TEXT, variant_axis TEXT, "
                "mode TEXT NOT NULL DEFAULT 'fixed', choose_n INTEGER NOT NULL DEFAULT 1, "
                "rechoose TEXT, source_filter TEXT, via_aura INTEGER NOT NULL DEFAULT 0, "
                "condition_kind TEXT)")
    cur.execute("CREATE TABLE grant_resistance_option (grant_id TEXT, damage_type_id TEXT)")

    cur.execute("CREATE TABLE grant_condition (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, condition_kind TEXT, condition_id TEXT, effect TEXT, "
                "via_aura INTEGER NOT NULL DEFAULT 0)")

    cur.execute("CREATE TABLE grant_save_advantage (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, scope_kind TEXT, ability_id TEXT, note TEXT, "
                "condition_kind TEXT)")

    # species-a grants poison resistance
    cur.execute("INSERT INTO grant_resistance VALUES "
                "('gre-species-a','species','species-a',NULL,'poison',NULL,'fixed',1,NULL,NULL,0,NULL)")
    # feat-gen grants fire resistance
    cur.execute("INSERT INTO grant_resistance VALUES "
                "('gre-feat-gen','feat','feat-gen',NULL,'fire',NULL,'fixed',1,NULL,NULL,0,NULL)")
    # sub-a at L3 grants charmed immunity
    cur.execute("INSERT INTO grant_condition VALUES "
                "('gcn-sub-a','subclass','sub-a',3,NULL,'charmed','immunity',0)")

    # ── state-effect materialization fixtures (T44b) ──────────────────────────
    # condition_kind marker: gates a grant so it materialises only while its state
    # is active (state_resistance_grants keys on condition_kind IS NOT NULL).
    cur.execute("CREATE TABLE condition_kind (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("INSERT INTO condition_kind VALUES ('state-active','State Active')")
    # gates for the two opposite size-damage riders (see grant_bonus fixtures below)
    cur.execute("INSERT INTO condition_kind VALUES ('grown','Grown')")
    cur.execute("INSERT INTO condition_kind VALUES ('shrunk','Shrunk')")

    # A class feature that grants a damage resistance only while its state is on:
    # owned by class_feature (never gathered by the CORE defenses walker) and gated
    # by condition_kind. Placed at a high level so no owner-enumeration picks it up.
    cur.execute("INSERT INTO class_feature VALUES ('cf-state','class-a',99,'State Feature A')")
    cur.execute("INSERT INTO grant_resistance VALUES "
                "('gre-state','class_feature','cf-state',NULL,'cold',NULL,'fixed',1,NULL,NULL,0,'state-active')")

    # Extra size rows so relative-step arithmetic and clamping have a real ordinal
    # ladder to walk ('size-a' already exists at ordinal 3).
    for sid, sname, sord, sft in [("size-t","Size T",1,2.5),("size-s","Size S",2,5.0),
                                   ("size-l","Size L",4,10.0),("size-h","Size H",5,15.0),
                                   ("size-g","Size G",6,20.0)]:
        cur.execute("INSERT INTO size VALUES (?,?,?,?)", (sid, sname, sord, sft))

    # A relative size-step grant mechanism owned by a size-changing spell, and a
    # creature carrying its own size for set-from-creature transformations.
    cur.execute("CREATE TABLE grant_size (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INTEGER, mode TEXT, step INTEGER, size_id TEXT, variant TEXT, "
                "condition_kind TEXT)")
    cur.execute("INSERT INTO grant_size VALUES "
                "('gsz-grow','spell','sp-grow',NULL,'step',1,NULL,'grow',NULL)")
    cur.execute("INSERT INTO grant_size VALUES "
                "('gsz-shrink','spell','sp-grow',NULL,'step',-1,NULL,'shrink',NULL)")
    cur.execute("INSERT INTO spell VALUES ('sp-grow','Spell-Grow',3,0)")

    # ── creature catalog (L15) + companion linkage (L21) ─────────────────────
    # Full creature statblock shape (mirrors the reference schema), plus the
    # grant_companion owner->creature spine. Content-neutral: SYNTHETIC creatures
    # only. 'creat-a' is retained (size-l) for the set-from-creature size lookups
    # used by the MODIFIER tests + size.py::creature_size.
    cur.execute("CREATE TABLE creature ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, size_id TEXT NOT NULL, "
                "creature_type_id TEXT NOT NULL, alignment_id TEXT, "
                "source_kind TEXT NOT NULL CHECK (source_kind IN ('appendix','subclass','spell')), "
                "source_id TEXT, ac_value INTEGER, ac_formula_note TEXT, hp_average INTEGER, "
                "hp_dice TEXT, hp_formula_note TEXT, initiative_bonus INTEGER, cr_text TEXT, "
                "xp INTEGER, pb INTEGER, description TEXT)")
    cur.execute("CREATE TABLE creature_ability (creature_id TEXT, ability_id TEXT, score INTEGER, "
                "PRIMARY KEY (creature_id, ability_id))")
    cur.execute("CREATE TABLE creature_speed (creature_id TEXT, movement_mode_id TEXT, feet INTEGER, "
                "formula_note TEXT, PRIMARY KEY (creature_id, movement_mode_id))")
    cur.execute("CREATE TABLE creature_sense (creature_id TEXT, sense_id TEXT, range_ft INTEGER, "
                "PRIMARY KEY (creature_id, sense_id))")
    cur.execute("CREATE TABLE creature_skill (creature_id TEXT, skill_id TEXT, bonus INTEGER, "
                "PRIMARY KEY (creature_id, skill_id))")
    cur.execute("CREATE TABLE creature_passive_perception (creature_id TEXT PRIMARY KEY, value INTEGER)")
    cur.execute("CREATE TABLE creature_resistance (creature_id TEXT, damage_type_id TEXT, note TEXT, "
                "PRIMARY KEY (creature_id, damage_type_id))")
    cur.execute("CREATE TABLE creature_immunity (creature_id TEXT, damage_type_id TEXT, "
                "condition_id TEXT, note TEXT, "
                "CHECK ((damage_type_id IS NULL) != (condition_id IS NULL)))")
    cur.execute("CREATE TABLE creature_vulnerability (creature_id TEXT, damage_type_id TEXT, "
                "PRIMARY KEY (creature_id, damage_type_id))")
    cur.execute("CREATE TABLE creature_trait (id TEXT PRIMARY KEY, creature_id TEXT, "
                "kind TEXT NOT NULL CHECK (kind IN ('trait','action','bonus_action','reaction')), "
                "name TEXT NOT NULL, body TEXT, atk_bonus INTEGER, atk_bonus_note TEXT, "
                "reach_ft INTEGER, range_text TEXT, dmg_average INTEGER, dmg_dice TEXT, "
                "damage_type_id TEXT, recharge_min INTEGER, uses_per_day INTEGER)")
    cur.execute("CREATE TABLE creature_formula (id TEXT PRIMARY KEY, creature_id TEXT, "
                "target TEXT NOT NULL, trait_id TEXT, form_note TEXT, base INTEGER, "
                "die_count INTEGER, die_faces INTEGER, round_mode TEXT)")
    cur.execute("CREATE TABLE creature_formula_term (formula_id TEXT, coefficient REAL, "
                "variable TEXT, above_level INTEGER, PRIMARY KEY (formula_id, variable))")
    cur.execute("CREATE TABLE grant_companion (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "creature_id TEXT, gained_at_level INTEGER, duration_amount INTEGER, "
                "duration_unit_id TEXT, at_spell_level INTEGER, notes TEXT)")

    # retained set-from-creature target (size lookups)
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind) "
                "VALUES ('creat-a','Creature A','size-l','type-a','appendix')")

    # creature-a: a rich statblock exercising every child reader
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind,ac_value,"
                "hp_average,hp_dice,initiative_bonus,cr_text,xp,pb) "
                "VALUES ('creature-a','Creature A2','size-a','type-a','appendix',13,10,'(3d6)',2,'1/4',50,2)")
    for aid, sc in [("a1", 12), ("a2", 14), ("a3", 10)]:
        cur.execute("INSERT INTO creature_ability VALUES ('creature-a',?,?)", (aid, sc))
    cur.execute("INSERT INTO creature_speed VALUES ('creature-a','walk',30,NULL)")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-a','fly',60,NULL)")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-a','swim',NULL,'equal to its Walk Speed')")
    cur.execute("INSERT INTO creature_sense VALUES ('creature-a','darkvision',60)")
    cur.execute("INSERT INTO creature_skill VALUES ('creature-a','sk1',4)")
    cur.execute("INSERT INTO creature_passive_perception VALUES ('creature-a',12)")
    cur.execute("INSERT INTO creature_resistance VALUES ('creature-a','fire',NULL)")
    cur.execute("INSERT INTO creature_immunity VALUES ('creature-a','poison',NULL,NULL)")
    cur.execute("INSERT INTO creature_immunity VALUES ('creature-a',NULL,'poisoned',NULL)")
    cur.execute("INSERT INTO creature_vulnerability VALUES ('creature-a','cold')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,body) "
                "VALUES ('ct-a-trait','creature-a','trait','Trait A','render-only text')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,atk_bonus,reach_ft,"
                "dmg_average,dmg_dice,damage_type_id) "
                "VALUES ('ct-a-act','creature-a','action','Action A',4,5,5,'1d6 + 2','fire')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,recharge_min,uses_per_day) "
                "VALUES ('ct-a-recharge','creature-a','action','Action B',5,3)")
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,base) "
                "VALUES ('cf-a-atk','creature-a','attack_bonus','ct-a-act',4)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-a-atk',1.0,'owner_proficiency_bonus',NULL)")

    # creature-b: header-only (exercises the empty-child cases)
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind) "
                "VALUES ('creature-b','Creature B','size-a','type-b','appendix')")

    # creature-c: a rich CONCRETE (fixed-stat) creature — NO creature_formula rows, so
    # is_templated() is False. Exercises the concrete companion deriver/validator over a
    # full statblock. Content-neutral: synthetic ids only.
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind,ac_value,"
                "hp_average,hp_dice,initiative_bonus,cr_text,xp,pb) "
                "VALUES ('creature-c','Creature C','size-a','type-a','appendix',12,7,'2d6',2,'1/8',25,2)")
    for aid, sc in [("a1", 8), ("a2", 16), ("a3", 12)]:
        cur.execute("INSERT INTO creature_ability VALUES ('creature-c',?,?)", (aid, sc))
    cur.execute("INSERT INTO creature_speed VALUES ('creature-c','walk',30,NULL)")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-c','fly',40,NULL)")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-c','swim',NULL,'equal to its Walk Speed')")
    cur.execute("INSERT INTO creature_sense VALUES ('creature-c','darkvision',90)")
    cur.execute("INSERT INTO creature_skill VALUES ('creature-c','sk1',4)")
    cur.execute("INSERT INTO creature_skill VALUES ('creature-c','sk2',2)")
    cur.execute("INSERT INTO creature_passive_perception VALUES ('creature-c',13)")
    cur.execute("INSERT INTO creature_resistance VALUES ('creature-c','fire',NULL)")
    cur.execute("INSERT INTO creature_immunity VALUES ('creature-c','poison',NULL,NULL)")
    cur.execute("INSERT INTO creature_immunity VALUES ('creature-c',NULL,'poisoned',NULL)")
    cur.execute("INSERT INTO creature_vulnerability VALUES ('creature-c','cold')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,body) "
                "VALUES ('ct-c-trait','creature-c','trait','Trait C','render-only text')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,atk_bonus,reach_ft,"
                "dmg_average,dmg_dice,damage_type_id) "
                "VALUES ('ct-c-bite','creature-c','action','Bite',5,5,4,'1d6 + 3','fire')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,recharge_min,uses_per_day) "
                "VALUES ('ct-c-recharge','creature-c','action','Recharge Move',5,2)")

    # creature-form: a CONCRETE self-transform form (T60). Fixed stat block (no
    # creature_formula rows), carrying a MENTAL ability score ('wisdom') so the
    # physical-transform retained-vs-replaced split can be exercised: a1/a2/a3 (physical)
    # are replaced by the form, 'wisdom' (mental) is retained by the character. Form
    # defences differ from the character's (cold, not fire) to prove replace-not-union.
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind,ac_value,"
                "hp_average,hp_dice,initiative_bonus,cr_text,xp,pb) "
                "VALUES ('creature-form','Creature Form','size-a','type-a','appendix',15,20,'3d8',1,'1',200,2)")
    for aid, sc in [("a1", 18), ("a2", 6), ("a3", 14), ("wisdom", 8)]:
        cur.execute("INSERT INTO creature_ability VALUES ('creature-form',?,?)", (aid, sc))
    cur.execute("INSERT INTO creature_speed VALUES ('creature-form','walk',40,NULL)")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-form','climb',20,NULL)")
    cur.execute("INSERT INTO creature_sense VALUES ('creature-form','darkvision',120)")
    cur.execute("INSERT INTO creature_resistance VALUES ('creature-form','cold',NULL)")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,atk_bonus,reach_ft,"
                "dmg_average,dmg_dice,damage_type_id) "
                "VALUES ('ct-form-claw','creature-form','action','Claw',6,5,11,'2d6 + 4','slashing')")

    # creature-t: a TEMPLATED spirit-like creature — NULL header ac/hp/pb, every
    # scaled stat driven by creature_formula rows. Exercises spell_level scaling,
    # spell_level_above_base thresholds, form_note gating (alternative forms),
    # multiattack (round down), and a save-forcing action. Owned by a synthetic
    # SPELL (base spell level 3). Content-neutral: synthetic ids only.
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind) "
                "VALUES ('creature-t','Creature T','size-a','type-a','spell')")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-t','walk',30,NULL)")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,atk_bonus_note) "
                "VALUES ('ctr-t-atk','creature-t','action','Strike','equals owner spell attack')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name) "
                "VALUES ('ctr-t-save','creature-t','action','Burst')")
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name) "
                "VALUES ('ctr-t-multi','creature-t','action','Multiattack')")
    # a save-forcing AURA (kind='trait', NOT an action): its scaled save DC must be
    # emitted by the deriver AND independently re-checked by the validator.
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name) "
                "VALUES ('ctr-t-aura','creature-t','trait','Aura')")
    # ac = 10 + spell_level
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-ac','creature-t','ac',NULL,NULL,10,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-ac',1.0,'spell_level',NULL)")
    # hp: two mutually-exclusive form variants (Form-X only / Form-Y only)
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-hpx','creature-t','hp',NULL,'Form-X only',20,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-hpx',5.0,'spell_level_above_base',3)")
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-hpy','creature-t','hp',NULL,'Form-Y only',30,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-hpy',5.0,'spell_level_above_base',3)")
    # pb = owner proficiency bonus
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-pb','creature-t','pb',NULL,NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-pb',1.0,'owner_proficiency_bonus',NULL)")
    # attack: bonus = spell attack modifier; damage = 1d8 + 3 + spell_level
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-atk','creature-t','attack_bonus','ctr-t-atk',NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-atk',1.0,'spell_attack_modifier',NULL)")
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-dmg','creature-t','attack_damage','ctr-t-atk',NULL,3,1,8,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-dmg',1.0,'spell_level',NULL)")
    # save DC = owner spell save DC
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-save','creature-t','save_dc','ctr-t-save',NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-save',1.0,'spell_save_dc',NULL)")
    # aura save DC (on the NON-action trait ctr-t-aura) = owner spell save DC
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-aura','creature-t','save_dc','ctr-t-aura',NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-aura',1.0,'spell_save_dc',NULL)")
    # multiattack = floor(spell_level / 2)
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-t-multi','creature-t','multiattack_count','ctr-t-multi',NULL,NULL,NULL,NULL,'down')")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-t-multi',0.5,'spell_level',NULL)")

    # creature-tb: a TEMPLATED beast-like creature — fixed ability scores (concrete),
    # but ac/hp/attack scaled by the OWNER's class level, wisdom modifier, and
    # proficiency bonus (no spell_level). Owned by a synthetic SUBCLASS.
    cur.execute("INSERT INTO creature (id,name,size_id,creature_type_id,source_kind) "
                "VALUES ('creature-tb','Creature TB','size-a','type-a','subclass')")
    cur.execute("INSERT INTO creature_speed VALUES ('creature-tb','walk',40,NULL)")
    for aid, sc in [("a1", 12), ("a2", 14), ("a3", 10)]:
        cur.execute("INSERT INTO creature_ability VALUES ('creature-tb',?,?)", (aid, sc))
    cur.execute("INSERT INTO creature_trait (id,creature_id,kind,name,atk_bonus_note) "
                "VALUES ('ctr-tb-atk','creature-tb','action','Maul','equals owner spell attack')")
    # ac = 13 + owner wisdom modifier
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-tb-ac','creature-tb','ac',NULL,NULL,13,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-tb-ac',1.0,'owner_wisdom_modifier',NULL)")
    # hp = 5 + 5 * owner class level
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-tb-hp','creature-tb','hp',NULL,NULL,5,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-tb-hp',5.0,'owner_class_level',NULL)")
    # pb = owner proficiency bonus
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-tb-pb','creature-tb','pb',NULL,NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-tb-pb',1.0,'owner_proficiency_bonus',NULL)")
    # attack: bonus = spell attack modifier; damage = 1d8 + 2 + owner wisdom modifier
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-tb-atk','creature-tb','attack_bonus','ctr-tb-atk',NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-tb-atk',1.0,'spell_attack_modifier',NULL)")
    cur.execute("INSERT INTO creature_formula (id,creature_id,target,trait_id,form_note,base,"
                "die_count,die_faces,round_mode) "
                "VALUES ('cf-tb-dmg','creature-tb','attack_damage','ctr-tb-atk',NULL,2,1,8,NULL)")
    cur.execute("INSERT INTO creature_formula_term VALUES ('cf-tb-dmg',1.0,'owner_wisdom_modifier',NULL)")

    # companion links: a synthetic spell owner (always-on, at spell level 2, 1-hour
    # duration) -> creature-a; a synthetic subclass owner gained at level 3 -> creature-b;
    # a synthetic spell owner (always-on, at spell level 1) -> concrete creature-c;
    # templated owners for creature-t (spell) and creature-tb (subclass).
    cur.execute("INSERT INTO grant_companion VALUES "
                "('gc-syn-spell','spell','sp-companion','creature-a',NULL,1,'hour',2,'synthetic summon')")
    cur.execute("INSERT INTO grant_companion VALUES "
                "('gc-syn-sub','subclass','sub-companion','creature-b',3,NULL,NULL,NULL,'synthetic subclass companion')")
    cur.execute("INSERT INTO grant_companion VALUES "
                "('gc-syn-concrete','spell','sp-comp-concrete','creature-c',NULL,NULL,NULL,1,'synthetic concrete companion')")
    cur.execute("INSERT INTO grant_companion VALUES "
                "('gc-syn-t','spell','sp-t','creature-t',NULL,1,'hour',3,'synthetic templated summon')")
    cur.execute("INSERT INTO grant_companion VALUES "
                "('gc-syn-tb','subclass','sub-t','creature-tb',3,NULL,NULL,NULL,'synthetic templated subclass companion')")

    # features domain: subclass_feature, species_trait, detail_option + additional class_feature rows
    # (class_feature table already exists from the feats domain section above)
    cur.execute("CREATE TABLE subclass_feature (id TEXT PRIMARY KEY, subclass_id TEXT, class_level INT, name TEXT)")
    cur.execute("CREATE TABLE species_trait (id TEXT PRIMARY KEY, species_id TEXT, name TEXT)")
    cur.execute("CREATE TABLE detail_option (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, axis TEXT, name TEXT, rechoose TEXT)")

    cur.execute("INSERT INTO class_feature VALUES ('cf-a1','class-a',1,'Feat A')")
    cur.execute("INSERT INTO class_feature VALUES ('cf-a2','class-a',1,'Feat B')")
    cur.execute("INSERT INTO class_feature VALUES ('cf-a3','class-a',2,'Feat C')")
    cur.execute("INSERT INTO class_feature VALUES ('cf-a4','class-a',3,'Feat D (one use)')")
    cur.execute("INSERT INTO class_feature VALUES ('cf-b1','class-b',1,'Feat X')")

    cur.execute("INSERT INTO subclass_feature VALUES ('sf-a1','sub-a',3,'Sub Feat A')")
    cur.execute("INSERT INTO subclass_feature VALUES ('sf-a2','sub-a',6,'Sub Feat B')")
    cur.execute("INSERT INTO subclass_feature VALUES ('sf-a3','sub-a',3,'Aspect of the Wilds')")

    cur.execute("INSERT INTO species_trait VALUES ('st-a1','species-a','Species Trait A')")

    cur.execute("INSERT INTO detail_option VALUES ('do-owl','subclass','sub-a','aspect','Owl',NULL)")
    cur.execute("INSERT INTO detail_option VALUES ('do-panther','subclass','sub-a','aspect','Panther',NULL)")

    cur.execute("INSERT INTO detail_option VALUES ('do-prot','class','class-a','school','Protector',NULL)")
    cur.execute("INSERT INTO detail_option VALUES ('do-thaum','class','class-a','school','Thaumaturge',NULL)")

    # weapon mastery domain: catalog_item, weapon, mastery_property tables
    cur.execute("CREATE TABLE IF NOT EXISTS mastery_property (id TEXT PRIMARY KEY, name TEXT)")
    cur.execute("INSERT OR IGNORE INTO mastery_property VALUES ('cleave','Cleave')")
    cur.execute("INSERT OR IGNORE INTO mastery_property VALUES ('vex','Vex')")
    cur.execute("INSERT OR IGNORE INTO mastery_property VALUES ('slow','Slow')")
    cur.execute("INSERT OR IGNORE INTO mastery_property VALUES ('nick','Nick')")
    cur.execute("CREATE TABLE IF NOT EXISTS catalog_item (id TEXT PRIMARY KEY, name TEXT, kind TEXT, "
                "category_id TEXT)")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('greataxe','Greataxe','weapon',NULL)")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('handaxe','Handaxe','weapon',NULL)")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('club','Club','weapon',NULL)")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('net','Net','weapon',NULL)")
    # rapier: a martial, finesse melee weapon -- exercises specific-weapon proficiency and the
    # finesse (max of str/dex) ability-mod choice in the attack-bonus derivation/validation
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('rapier','Rapier','weapon',NULL)")
    # T35: catalog_item entries for equipment used in inventory tests
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('chain-mail','Chain Mail','armor','armor')")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('leather-armor','Leather Armor','armor','armor')")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('half-plate','Half Plate Armor','armor','armor')")
    cur.execute("INSERT OR IGNORE INTO catalog_item VALUES ('shield','Shield','armor','shield')")
    cur.execute("CREATE TABLE IF NOT EXISTS weapon (id TEXT PRIMARY KEY REFERENCES catalog_item(id), "
                "tier_id TEXT, range_class_id TEXT, dmg_dice_count INT, dmg_die_faces INT, "
                "dmg_flat INT, damage_type_id TEXT, mastery_id TEXT REFERENCES mastery_property(id))")
    cur.execute("INSERT OR IGNORE INTO weapon VALUES ('greataxe','martial','melee',1,12,NULL,'slashing','cleave')")
    cur.execute("INSERT OR IGNORE INTO weapon VALUES ('handaxe','simple','melee',1,6,NULL,'slashing','vex')")
    cur.execute("INSERT OR IGNORE INTO weapon VALUES ('club','simple','melee',1,4,NULL,'bludgeoning','slow')")
    cur.execute("INSERT OR IGNORE INTO weapon VALUES ('net','martial','ranged',NULL,NULL,NULL,NULL,NULL)")
    cur.execute("INSERT OR IGNORE INTO weapon VALUES ('rapier','martial','melee',1,8,NULL,'piercing',NULL)")

    # B5: item_slot dimension table — all body slots for equipping items
    cur.execute("CREATE TABLE item_slot (id TEXT PRIMARY KEY, name TEXT)")
    for sid, sname in [
        ("armor", "Armor"), ("shield", "Shield"),
        ("main_hand", "Main Hand"), ("off_hand", "Off Hand"),
        ("finger_1", "Finger 1"), ("finger_2", "Finger 2"),
        ("head", "Head"), ("neck", "Neck"), ("back", "Back"),
        ("waist", "Waist"), ("hands", "Hands"), ("wrists", "Wrists"),
        ("feet", "Feet"),
    ]:
        cur.execute("INSERT INTO item_slot VALUES (?,?)", (sid, sname))

    # T35: inventory-validator test infrastructure
    cur.execute("CREATE TABLE rarity (id TEXT PRIMARY KEY, name TEXT, ordinal INT)")
    for rid, rname, rord in [("common","Common",1),("uncommon","Uncommon",2),
                               ("rare","Rare",3),("varies","Varies",4)]:
        cur.execute("INSERT INTO rarity VALUES (?,?,?)", (rid, rname, rord))

    cur.execute("CREATE TABLE weapon_property_vocab (id TEXT PRIMARY KEY, name TEXT, "
                "takes_param INT DEFAULT 0, param_kind TEXT, description TEXT)")
    for pid, pname in [("two-handed","Two-Handed"),("versatile","Versatile"),
                       ("finesse","Finesse"),("light","Light")]:
        cur.execute("INSERT INTO weapon_property_vocab (id,name) VALUES (?,?)", (pid, pname))

    cur.execute("CREATE TABLE weapon_property_map (weapon_id TEXT, property_id TEXT, "
                "range_normal INT, range_long INT, param_die_faces INT, ammunition_type_id TEXT, "
                "note TEXT)")
    # greataxe: two-handed | handaxe: light | pike: two-handed + versatile | rapier: finesse
    for wid, pid in [("greataxe","two-handed"),("pike","two-handed"),
                     ("pike","versatile"),("handaxe","light"),("rapier","finesse")]:
        cur.execute("INSERT INTO weapon_property_map (weapon_id,property_id) VALUES (?,?)",
                    (wid, pid))

    cur.execute("CREATE TABLE magic_item (id TEXT PRIMARY KEY REFERENCES catalog_item(id), "
                "rarity_id TEXT, requires_attunement INT DEFAULT 0, attune_req_kind TEXT, "
                "attune_req_value TEXT, consumable INT DEFAULT 0, effect_duration TEXT, "
                "description TEXT, cumulative_max_seconds INT)")
    cur.execute("INSERT INTO catalog_item VALUES ('mi-scroll','Magic Scroll','wondrous','scroll')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,consumable,description) "
                "VALUES ('mi-scroll','common',1,'Spell Scroll')")
    cur.execute("INSERT INTO catalog_item VALUES ('mi-sword','Magic Sword','weapon',NULL)")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) "
                "VALUES ('mi-sword','rare',1)")
    cur.execute("INSERT INTO catalog_item VALUES ('mi-shield','Magic Shield','armor','shield')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) "
                "VALUES ('mi-shield','uncommon',1)")

    cur.execute("CREATE TABLE magic_item_template (id INTEGER PRIMARY KEY, template_id TEXT, "
                "base_kind TEXT, tier_id TEXT, range_class_id TEXT, base_item_id TEXT)")
    cur.execute("INSERT INTO magic_item_template (template_id,base_kind,base_item_id) "
                "VALUES ('tpl-weapon-1','weapon','greataxe')")
    cur.execute("INSERT INTO magic_item_template (template_id,base_kind,base_item_id) "
                "VALUES ('tpl-shield','shield','mi-shield')")

    cur.execute("CREATE TABLE item_category (id TEXT PRIMARY KEY, kind TEXT, book_tier TEXT, "
                "book_class TEXT, family TEXT, subtype TEXT)")
    for icid, ickind in [("weapon","gear"),("scroll","gear"),("armor","gear"),("shield","gear")]:
        cur.execute("INSERT INTO item_category (id,kind) VALUES (?,?)", (icid, ickind))

    # T36a: derivation-engine infrastructure tables
    cur.execute("CREATE TABLE grant_bonus (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, condition_kind TEXT, target_kind TEXT, target_id TEXT, value INT, "
                "die_count INT, die_faces INT, damage_type_id TEXT, scope_note TEXT, source_name TEXT)")
    # AC bonus from feat, initiative bonus, save bonus from subclass, AC from spell, save from spell
    for gbid, okind, oid, tkind, val, sn in [
        ("gb-ac-feat","feat","feat-gen","ac",1,"feat-gen"),
        ("gb-init-feat","feat","feat-gen","initiative",2,"feat-gen"),
        ("gb-save-sub","subclass","sub-a","saving_throw",1,"sub-a"),
        ("gb-ac-spell","spell","sp1","ac",2,"shield-of-faith"),
        ("gb-save-spell","spell","sp2","saving_throw",None,"bless"),
        ("gb-ac-spell2","spell","sp1","ac",1,"shield-of-faith"),
        ("gb-wpn-atk","spell","sp3","weapon_attack",1,"magic-weapon"),
        ("gb-wpn-dmg","spell","sp3","weapon_damage",1,"magic-weapon"),
    ]:
        cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,target_kind,value,source_name) "
                    "VALUES (?,?,?,?,?,?)", (gbid, okind, oid, tkind, val, sn))

    # T44b: two opposite state-gated extra-damage riders on the size-changing spell.
    # A dice-only grant (value NULL); condition_kind gates it to a single state id so the
    # grow rider (+1d4) and shrink rider (-1d4, negative die_count) never leak into each
    # other. Owned by 'sp-grow' (which also owns the grant_size step rows).
    for gbid, dc, ck in [("gb-xd-grow", 1, "grown"), ("gb-xd-shrink", -1, "shrunk")]:
        cur.execute("INSERT INTO grant_bonus "
                    "(id,owner_kind,owner_id,target_kind,value,die_count,die_faces,condition_kind) "
                    "VALUES (?,'spell','sp-grow','extra_damage',NULL,?,4,?)", (gbid, dc, ck))

    cur.execute("CREATE TABLE grant_d20_modifier (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "owner_kind TEXT, owner_id TEXT, gained_at_level INT, condition_kind TEXT, "
                "target_kind TEXT, ability_id TEXT, modifier_id TEXT, "
                "source_name TEXT, scope_note TEXT)")
    cur.execute("INSERT INTO grant_d20_modifier (owner_kind,owner_id,target_kind,modifier_id,source_name) "
                "VALUES ('feat','feat-gen','initiative','advantage','feat-gen')")

    cur.execute("CREATE TABLE armor (id TEXT PRIMARY KEY REFERENCES catalog_item(id), "
                "category_id TEXT, base_ac INT, dex_cap INT, ac_bonus INT, strength_req INT, "
                "stealth_disadvantage INT DEFAULT 0)")
    cur.execute("INSERT INTO catalog_item VALUES ('chain-mail-armor','Chain Mail','armor','armor')")
    cur.execute("INSERT INTO armor VALUES ('chain-mail-armor','heavy',16,0,NULL,13,1)")
    cur.execute("INSERT INTO catalog_item VALUES ('leather-armor-item','Leather Armor','armor','armor')")
    cur.execute("INSERT INTO armor VALUES ('leather-armor-item','light',11,NULL,NULL,NULL,0)")
    cur.execute("INSERT INTO catalog_item VALUES ('shield-item','Shield','armor','shield')")
    cur.execute("INSERT INTO armor VALUES ('shield-item','shield',NULL,NULL,2,NULL,0)")

    cur.execute("CREATE TABLE ac_formula (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, base INT DEFAULT 10, allows_shield INT)")
    cur.execute("INSERT INTO ac_formula VALUES ('acf-a','class','class-a',NULL,10,0)")
    cur.execute("CREATE TABLE ac_formula_ability (formula_id TEXT, ability_id TEXT)")
    cur.execute("INSERT INTO ac_formula_ability VALUES ('acf-a','a2')")

    cur.execute("CREATE TABLE grant_resource (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                "gained_at_level INT, condition_kind TEXT, name TEXT, uses_kind TEXT, uses_num INT, "
                "uses_ability_id TEXT)")
    cur.execute("INSERT INTO grant_resource VALUES ('gr-a1','class','class-a',NULL,NULL,'Class Resource A',"
                "'per_long_rest',2,NULL)")

    # B9: state dimension table + state_compatibility junction table
    cur.execute("CREATE TABLE state (id TEXT PRIMARY KEY, name TEXT)")
    state_ids = [
        # 15 conditions from the condition table
        "blinded", "charmed", "deafened", "exhausted", "frightened",
        "grappled", "incapacitated", "invisible", "paralyzed", "petrified",
        "poisoned", "prone", "restrained", "stunned", "unconscious",
        # NEW states beyond conditions (T29 § "15 conditions + NEW states")
        "raging", "wild_shaped", "starry_form", "hasted", "blessed",
        "polymorphed", "enlarged", "reduced", "hidden", "dodging",
        "readying", "concentrating", "inspired", "stabilized",
        "boots_of_speed_active", "shield_of_faith",
    ]
    for sid in state_ids:
        cur.execute("INSERT INTO state VALUES (?,?)", (sid, sid.title().replace("_", " ")))

    cur.execute("CREATE TABLE state_compatibility ("
                "blocking_state_id TEXT NOT NULL REFERENCES state(id), "
                "blocked_state_id TEXT NOT NULL REFERENCES state(id), "
                "kind TEXT NOT NULL CHECK(kind IN ('blocks', 'implies')), "
                "PRIMARY KEY (blocking_state_id, blocked_state_id, kind))")
    # 14 rows per T29 (5 implies + 9 blocks)
    implies = [
        ("unconscious", "incapacitated"), ("unconscious", "prone"),
        ("petrified", "incapacitated"), ("paralyzed", "incapacitated"),
        ("stunned", "incapacitated"),
    ]
    blocks = [
        ("incapacitated", "raging"), ("incapacitated", "concentrating"),
        ("incapacitated", "dodging"), ("incapacitated", "readying"),
        ("incapacitated", "wild_shaped"),
        ("raging", "concentrating"),
        ("petrified", "poisoned"),
        ("polymorphed", "raging"), ("polymorphed", "wild_shaped"),
    ]
    for blk, bd in implies:
        cur.execute("INSERT INTO state_compatibility VALUES (?,?,'implies')", (blk, bd))
    for blk, bd in blocks:
        cur.execute("INSERT INTO state_compatibility VALUES (?,?,'blocks')", (blk, bd))

    # B3: condition_effect table — representative subset for test coverage
    cur.execute("CREATE TABLE condition_effect ("
                "id INTEGER PRIMARY KEY, "
                "condition_id TEXT NOT NULL REFERENCES condition(id), "
                "effect_kind TEXT NOT NULL, target_kind TEXT, target_id TEXT, "
                "modifier TEXT NOT NULL, source_scope TEXT, note TEXT)")
    test_conditions = [
        ("blinded", "attack_disadvantage", "attack", None, "disadvantage", "self_vs_others", ""),
        ("blinded", "attacks_advantage_against", "attack", None, "advantage", "others_vs_self", ""),
        ("incapacitated", "action_blocked", "action", None, "blocked", "self", ""),
        ("incapacitated", "reaction_blocked", "reaction", None, "blocked", "self", ""),
        ("poisoned", "attack_disadvantage", "attack", None, "disadvantage", "self_vs_others", ""),
        ("unconscious", "attacks_advantage_against", "attack", None, "advantage", "others_vs_self", ""),
        ("prone", "crawl_only", "movement", None, "crawl_only", "self", ""),
    ]
    cur.executemany("INSERT INTO condition_effect (condition_id, effect_kind, target_kind, target_id, modifier, source_scope, note) VALUES (?,?,?,?,?,?,?)", test_conditions)

    # B11: add pact_slot to grant_spell recovery CHECK in test DB
    # Replace the minimal 4-col grant_spell with one that has the expanded CHECK.
    cur.execute("""CREATE TABLE grant_spell_new_t (
        id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, gained_at_level INT,
        bucket TEXT, recovery TEXT CHECK (recovery IN
          ('at_will','spell_slot','pact_slot','slotless_per_rest','ritual_only')),
        condition_kind TEXT, uses_kind TEXT,
        uses_ability_id TEXT, uses_resource_id TEXT, uses_num INTEGER,
        recharge_id TEXT, also_slot_castable INTEGER, ability_mode TEXT,
        ability_id TEXT, choice_group INTEGER, note TEXT
    )""")
    cur.execute("INSERT INTO grant_spell_new_t (id, owner_kind, owner_id, gained_at_level) "
                "SELECT id, owner_kind, owner_id, gained_at_level FROM grant_spell")
    cur.execute("DROP TABLE grant_spell")
    cur.execute("ALTER TABLE grant_spell_new_t RENAME TO grant_spell")

    # ── grant-only subclass test data ──
    cur.execute("INSERT INTO subclass VALUES ('sub-shadow','class-m','Sub Shadow',0,'')")
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery,ability_mode,ability_id) "
                "VALUES ('gsp-sub-shadow','subclass','sub-shadow','cantrip','at_will','fixed','a1')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-sub-shadow','sp1')")

    # ── T34 isolated test data: new entities + grant rows (IDs NOT referenced by existing tests) ──

    cur.execute("INSERT INTO recharge_cadence VALUES ('short-rest','Short Rest')")

    cur.execute("INSERT INTO subclass VALUES ('sub-widen','class-a','Sub Widen',0,'')")

    cur.execute("INSERT INTO species VALUES ('species-slotless','Species Slotless','type-a',30,'')")

    cur.execute("INSERT INTO detail_option VALUES ('detail-widen','class','class-a','axis-test','Detail A',NULL)")

    cur.execute("INSERT INTO class_option VALUES ('class-opt-widen','test-catalog','class','class-a',"
                "'Class Opt A',NULL,NULL,NULL,0,'')")

    cur.execute("INSERT INTO spell VALUES ('sp1-ritual','Sp1 Ritual',1,1)")

    # subclass grant_spell with class_list choice (Magical Secrets analog on a subclass)
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery) "
                "VALUES ('gsp-sub-list','subclass','sub-widen','always','spell_slot')")
    cur.execute("INSERT INTO grant_spell_choice (grant_id,from_kind) VALUES ('gsp-sub-list','class_list')")
    cur.execute("INSERT INTO grant_spell_choice_value VALUES ('gsp-sub-list','class-b')")

    # ritual-only spell grant on same subclass
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery) "
                "VALUES ('gsp-ritual','subclass','sub-widen','always','ritual_only')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-ritual','sp1-ritual')")

    # slotless-per-rest grant with uses on species-slotless
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery,uses_num,recharge_id) "
                "VALUES ('gsp-slotless','species','species-slotless','always','slotless_per_rest',3,'short-rest')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-slotless','sp2')")

    # class_detail grant_spell with class_list choice (Thaumaturge analog)
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery) "
                "VALUES ('gsp-cls-det','class_detail','detail-widen','cantrip','at_will')")
    cur.execute("INSERT INTO grant_spell_choice (grant_id,from_kind) VALUES ('gsp-cls-det','class_list')")
    cur.execute("INSERT INTO grant_spell_choice_value VALUES ('gsp-cls-det','class-b')")

    # class_option grant_spell with class_list choice (Pact of the Tome analog)
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery) "
                "VALUES ('gsp-cls-opt','class_option','class-opt-widen','cantrip','at_will')")
    cur.execute("INSERT INTO grant_spell_choice (grant_id,from_kind) VALUES ('gsp-cls-opt','class_list')")
    cur.execute("INSERT INTO grant_spell_choice_value VALUES ('gsp-cls-opt','class-b')")

    # ── F05-T39 fixtures ──────────────────────────────────────────────────────
    # T34 (GRIMOIRE deriver): cantrip-recovery force + dynamic per-rest use counts.
    # S12 (validators) + MODIFIER deriver: item-sourced senses/speeds/save bonuses.
    # All IDs are new and unreferenced by existing tests.

    # spells: one cantrip (level 0) + three level-1 spells for the dynamic-uses grants
    for _sid, _sname, _slvl in [("spc0", "Spc0", 0), ("spd1", "Spd1", 1),
                                ("spd2", "Spd2", 1), ("spd3", "Spd3", 1)]:
        cur.execute("INSERT INTO spell VALUES (?,?,?,0)", (_sid, _sname, _slvl))

    # feats that own the new grants (resolved by id in the tests)
    for _fid, _fname in [("feat-cantrip", "Feat Cantrip"), ("feat-dyn-pb", "Feat Dyn PB"),
                         ("feat-dyn-am", "Feat Dyn AM"), ("feat-dyn-cr", "Feat Dyn CR")]:
        cur.execute("INSERT INTO feat VALUES (?,?,'general',0)", (_fid, _fname))

    # a class resource with a count ladder (for the class_resource dynamic-uses kind),
    # owned by class-a so the level is taken from the character's class-a level
    cur.execute("INSERT INTO class_resource VALUES ('cr-dyn','class','class-a','Dyn Resource')")
    cur.execute("INSERT INTO class_resource_level VALUES ('cr-dyn',1,4,NULL,NULL,NULL)")

    # step 1: a cantrip grant whose stated recovery is 'spell_slot' — the deriver must
    # force it to 'at_will' because the granted spell is level 0
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery) "
                "VALUES ('gsp-cantrip-slot','feat','feat-cantrip','cantrip','spell_slot')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-cantrip-slot','spc0')")

    # step 2: dynamic-uses grants (uses_num NULL), one per dynamic uses_kind. ability_id
    # is set so derive_sources creates a feat spellcasting source for each grant.
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery,uses_kind,ability_id) "
                "VALUES ('gsp-dyn-pb','feat','feat-dyn-pb','always','slotless_per_rest','proficiency_bonus','a1')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-dyn-pb','spd1')")
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery,uses_kind,uses_ability_id,ability_id) "
                "VALUES ('gsp-dyn-am','feat','feat-dyn-am','always','slotless_per_rest','ability_modifier','a4','a4')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-dyn-am','spd2')")
    cur.execute("INSERT INTO grant_spell (id,owner_kind,owner_id,bucket,recovery,uses_kind,uses_resource_id,ability_id) "
                "VALUES ('gsp-dyn-cr','feat','feat-dyn-cr','always','slotless_per_rest','class_resource','cr-dyn','a1')")
    cur.execute("INSERT INTO grant_spell_fixed VALUES ('gsp-dyn-cr','spd3')")

    # step 3/4: magic items conferring senses/speeds/save bonuses.
    # attuned item — darkvision 60 + fly 30 (materialise at MODIFIER only when attuned)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-boots','Boots Alpha','wondrous','feet')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-boots','rare',1)")
    cur.execute("INSERT INTO grant_sense VALUES ('gs-mi-boots','magic_item','mi-boots',NULL,'darkvision',60,0,NULL,NULL)")
    cur.execute("INSERT INTO grant_speed VALUES ('gsp-mi-boots','magic_item','mi-boots',NULL,'fly',30,0,1,0,NULL,NULL)")
    # passive-on-equip item (no attunement) — blindsight 10 while equipped
    cur.execute("INSERT INTO catalog_item VALUES ('mi-goggles','Goggles Alpha','wondrous','head')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-goggles','uncommon',0)")
    cur.execute("INSERT INTO grant_sense VALUES ('gs-mi-goggles','magic_item','mi-goggles',NULL,'blindsight',10,0,NULL,NULL)")
    # two attuned items, each granting +1 to all saves (they stack to +2)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-ring','Ring Alpha','wondrous','finger_1')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-ring','rare',1)")
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,target_kind,target_id,value,source_name) "
                "VALUES ('gb-mi-ring','magic_item','mi-ring','saving_throw',NULL,1,'Ring Alpha')")
    cur.execute("INSERT INTO catalog_item VALUES ('mi-cloak','Cloak Alpha','wondrous','back')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-cloak','rare',1)")
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,target_kind,target_id,value,source_name) "
                "VALUES ('gb-mi-cloak','magic_item','mi-cloak','saving_throw',NULL,1,'Cloak Alpha')")
    # attuned item granting +2 to ONE ability's save (target_id set = per-ability)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-amulet','Amulet Alpha','wondrous','neck')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-amulet','rare',1)")
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,target_kind,target_id,value,source_name) "
                "VALUES ('gb-mi-amulet','magic_item','mi-amulet','saving_throw','a1',2,'Amulet Alpha')")
    # non-attunement item with an ADDITIVE walk speed (+10) while equipped — used to
    # prove a spuriously-attuned equipped item isn't double-counted (branch 1 + 2)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-anklet','Anklet Alpha','wondrous','feet')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-anklet','uncommon',0)")
    cur.execute("INSERT INTO grant_speed VALUES ('gsp-mi-anklet','magic_item','mi-anklet',NULL,'walk',10,0,0,1,NULL,NULL)")

    # T47/T48 fixtures: item ability-set grants + a weapon-attack bonus item.
    # attuned item that SETS ability a1 to 19 (grant_ability_set mode='set') -- when equipped +
    # attuned, effective a1 is overridden to 19 (used by the effective-ability exact check)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-belt','Belt Alpha','wondrous','waist')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-belt','rare',1)")
    cur.execute("INSERT INTO grant_ability_set VALUES ('gas-mi-belt','magic_item','mi-belt',NULL,'a1',19,'set',NULL)")
    # attuned item that SETS a1 to 12 -- BELOW the fixture base (14); locks 'set' as a true override
    # (pulls the score DOWN to 12) rather than a floor (which would keep 14)
    cur.execute("INSERT INTO catalog_item VALUES ('mi-band','Band Alpha','wondrous','waist')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-band','rare',1)")
    cur.execute("INSERT INTO grant_ability_set VALUES ('gas-mi-band','magic_item','mi-band',NULL,'a1',12,'set',NULL)")
    # attuned item granting +1 to every weapon attack (grant_bonus target_kind='weapon_attack')
    cur.execute("INSERT INTO catalog_item VALUES ('mi-charm','Charm Alpha','wondrous','waist')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-charm','rare',1)")
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,target_kind,target_id,value,source_name) "
                "VALUES ('gb-mi-charm','magic_item','mi-charm','weapon_attack',NULL,1,'Charm Alpha')")
    # T47 cross-owner symmetry: an always-on species-owned ability-set grant (a NON-item owner) --
    # exercises the validator's ability-set re-derivation across owner kinds. species-a SETs a2 to
    # 20. No sheet in the default fixture carries species-a, so this is inert unless a test opts in.
    cur.execute("INSERT INTO grant_ability_set VALUES ('gas-species-a','species','species-a',NULL,'a2',20,'set',NULL)")

    # T51 fixtures: an attuned magic WEAPON that owns exactly one extra_damage rider.
    # Blade Alpha is a martial melee weapon (so derive_attacks DOES produce an attack for it) AND a
    # magic item requiring attunement, owning a single grant_bonus(target_kind='extra_damage', +1d6).
    # The rider folds into THAT weapon's own attack, and only while the item is attuned.
    cur.execute("INSERT INTO catalog_item VALUES ('mi-blade','Blade Alpha','weapon',NULL)")
    cur.execute("INSERT INTO weapon VALUES ('mi-blade','martial','melee',1,8,NULL,'slashing',NULL)")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-blade','rare',1)")
    cur.execute("INSERT INTO grant_bonus "
                "(id,owner_kind,owner_id,target_kind,value,die_count,die_faces,damage_type_id) "
                "VALUES ('gb-blade-xd','magic_item','mi-blade','extra_damage',NULL,1,6,'fire')")

    # T50 fixtures: a CON-set item (amulet-of-health analog) + a state-gated HP boost feature +
    # an always-on (non-state) grant_hp that must stay INERT in the effective-CON max-HP recompute.
    # Vigor Alpha SETs a3 to 18 while attuned; tests alias a3's abbrev to 'con' in their own private
    # DB copy so the deriver/validator resolve it as the constitution ability.
    cur.execute("INSERT INTO catalog_item VALUES ('mi-vigor','Vigor Alpha','wondrous','neck')")
    cur.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES ('mi-vigor','rare',1)")
    cur.execute("INSERT INTO grant_ability_set VALUES ('gas-mi-vigor','magic_item','mi-vigor',NULL,'a3',18,'set',NULL)")
    # a class feature that grants +5 max HP only while its state is active (high level so no
    # owner-enumeration reaches it) -- lets a test combine a state grant_hp WITH the CON-delta.
    cur.execute("INSERT INTO class_feature VALUES ('cf-hp-state','class-a',99,'HP State Feature A')")
    cur.execute("INSERT INTO grant_hp VALUES ('ghp-state','class_feature','cf-hp-state',NULL,5,NULL,'state-active')")
    # an always-on grant_hp on feat-gen -- never gathered under an active state, so it must NOT
    # reach max_boost (guards the deriver's and validator's state-only HP accumulation).
    cur.execute("INSERT INTO grant_hp VALUES ('ghp-feat','feat','feat-gen',NULL,7,NULL,NULL)")

    con.commit()
    con.close()


@pytest.fixture
def rules_db(tmp_path) -> str:
    p = tmp_path / "rules.db"
    _build_rules_db(str(p))
    return str(p)


@pytest.fixture
def access(rules_db):
    from access.validator import ValidatorAccess   # lazy: the package is created in this task
    return ValidatorAccess(path=rules_db)
