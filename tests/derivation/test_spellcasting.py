"""Spellcasting stats: save DC + attack per caster, multi-caster, non-caster."""
from app.derivation import spellcasting


def _scores(**over):
    s = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    s.update(over)
    return s


def test_spell_stats(catalog):
    out = spellcasting.spell_stats(catalog, _scores(int=18), 3, [("mage", 5)])
    assert out["Mage"] == {"ability": "int", "save_dc": 15, "attack_bonus": 7}
    assert spellcasting.spell_stats(catalog, _scores(), 2, [("warrior", 3)]) == {}     # non-caster


def test_multiclass_two_casters_each_get_spell_stats(catalog):
    out = spellcasting.spell_stats(catalog, _scores(int=18, wis=14), 3, [("mage", 5), ("oracle", 3)])
    assert out["Mage"]["save_dc"] == 15 and out["Oracle"]["save_dc"] == 13              # int vs wis


def test_spellbook_drops_unknown_spell_name(catalog):
    # an unknown leveled name is dropped, not mis-bucketed at level 1
    choices = {"classes": [{"class": "Mage", "level": 5}],
               "spell_choices": {"cantrips": ["Spark"], "spells": ["Bolt", "Bogus Spell"]}}
    names = [s["name"] for s in spellcasting.spellbook(catalog, choices)]
    assert "Bolt" in names and "Spark" in names and "Bogus Spell" not in names


def test_spell_slots(catalog):
    assert spellcasting.spell_slots(catalog, [("mage", 5)]) == {1: 4, 2: 3, 3: 2}        # single-class unchanged
    assert spellcasting.spell_slots(catalog, [("warrior", 3)]) == {}                    # non-caster


def test_spell_slots_multiclass_uses_combined_level(catalog):
    # combined caster level 5 (full 2 + full 3), NOT the old per-class sum {1:7, 2:2}
    assert spellcasting.spell_slots(catalog, [("mage", 2), ("oracle", 3)]) == {1: 4, 2: 3, 3: 2}


def test_spell_slots_third_caster_subclass(catalog):
    # Arcane Trickster rogue 9 → third caster → caster level 3 → {1:4, 2:2}; plain rogue → none
    assert spellcasting.spell_slots(catalog, [("rogue", 9, "Arcane Trickster")]) == {1: 4, 2: 2}
    assert spellcasting.spell_slots(catalog, [("rogue", 9, None)]) == {}


def test_combined_caster_level_raw_rules():
    # full +level, half +level//2, third-caster subclass +level//3; pact (warlock) excluded
    prog = {"paladin": "half", "sorcerer": "full", "warlock": "pact"}
    thirds = {"eldritchknight", "arcanetrickster"}
    cl = spellcasting._combined_caster_level
    assert cl(prog, thirds, [("paladin", 6), ("sorcerer", 2)]) == 5
    assert cl(prog, thirds, [("paladin", 6), ("sorcerer", 2), ("warlock", 3)]) == 5     # pact excluded
    assert cl(prog, thirds, [("fighter", 7, "Eldritch Knight")]) == 2                   # 7 // 3
    assert cl({"fighter": None}, thirds, [("fighter", 6, None)]) == 0                   # non-caster


def test_spellbook_buckets_by_level_known_caster(catalog):
    book = spellcasting.spellbook(catalog, {"classes": [{"class": "Mage", "level": 5}],
                                            "spell_choices": {"cantrips": ["Spark"], "spells": ["Bolt", "Quake"]}})
    assert {"name": "Spark", "level": 0, "prepared": False} in book
    assert next(b for b in book if b["name"] == "Bolt") == {"name": "Bolt", "level": 1, "prepared": False}
    assert next(b for b in book if b["name"] == "Quake")["level"] == 2                  # real spell level


def test_spellbook_prepared_for_prepared_caster(catalog):
    book = spellcasting.spellbook(catalog, {"classes": [{"class": "Oracle", "level": 3}],
                                            "spell_choices": {"cantrips": [], "spells": ["Bolt"]}})
    assert book[0]["prepared"] is True                                                 # oracle = prepared


def test_spellbook_includes_feature_granted_spells(catalog):
    # Arcane Trickster: at_cantrips/at_spells are separate choice fields, all known
    book = spellcasting.spellbook(catalog, {"classes": [{"class": "Rogue", "level": 3}],
                                            "at_cantrips": ["Wiz Cantrip A"], "at_spells": ["Evoke Bolt", "Charm Word"]})
    by = {b["name"]: b for b in book}
    assert by["Wiz Cantrip A"] == {"name": "Wiz Cantrip A", "level": 0, "prepared": False}
    assert by["Evoke Bolt"] == {"name": "Evoke Bolt", "level": 1, "prepared": False}   # known, real level


def test_spellbook_handles_single_string_cantrip_field(catalog):
    book = spellcasting.spellbook(catalog, {"classes": [{"class": "Druid", "level": 2}],
                                            "bonus_cantrip": "Druid Spark"})           # n==1 → bare string
    assert {"name": "Druid Spark", "level": 0, "prepared": False} in book


def test_spellbook_dedupes_across_sources(catalog):
    book = spellcasting.spellbook(catalog, {"classes": [{"class": "Mage", "level": 5}],
                                            "spell_choices": {"cantrips": ["Spark"], "spells": ["Bolt"]},
                                            "at_cantrips": ["Spark"]})                 # Spark in two sources
    assert [b["name"] for b in book].count("Spark") == 1
