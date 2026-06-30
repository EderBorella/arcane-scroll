"""Vitals & movement: HP (incl. the multiclass first-level rule), hit dice, AC, speed."""
from app.derivation import vitals


def _scores(**over):
    s = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    s.update(over)
    return s


def test_max_hp_and_hit_dice(catalog):
    assert vitals.max_hp(catalog, [("warrior", 3)], 2) == 28        # (10+2) + (6+2) + (6+2)
    assert vitals.hit_dice(catalog, [("warrior", 3), ("mage", 2)]) == {"d10": 3, "d6": 2}


def test_multiclass_hp_only_first_level_is_maxed(catalog):
    # primary = mage (d6) maxed at L1; every later level averages; +1 CON each
    assert vitals.max_hp(catalog, [("mage", 3), ("warrior", 2)], 1) == 31


def test_armor_class_unarmored_and_defences(catalog):
    assert vitals.armor_class(_scores(dex=16), [("mage", 5)]) == 13           # 10 + DEX
    assert vitals.armor_class(_scores(dex=14, con=16), [("barbarian", 3)]) == 15   # +CON
    assert vitals.armor_class(_scores(dex=14, wis=16), [("monk", 3)]) == 15        # +WIS


def test_armor_class_worn(catalog):
    heavy = {"armor_class": {"base": 16, "dex_bonus": False}}
    light = {"armor_class": {"base": 11, "dex_bonus": True}}
    medium = {"armor_class": {"base": 15, "dex_bonus": True, "max_bonus": 2}}
    assert vitals.armor_class(_scores(dex=18), [("fighter", 5)], heavy) == 16            # heavy: no Dex
    assert vitals.armor_class(_scores(dex=14), [("rogue", 5)], light) == 13              # light: +full Dex
    assert vitals.armor_class(_scores(dex=18), [("cleric", 5)], medium) == 17            # medium: Dex capped at 2
    assert vitals.armor_class(_scores(dex=14), [("fighter", 5)], heavy, shield=True) == 18  # +2 shield


def test_armor_class_medium_without_max_bonus_caps_dex(catalog):
    # a medium-armour record missing max_bonus must still cap Dex at +2 (not grant full Dex)
    medium = {"armor_category": "Medium", "armor_class": {"base": 14, "dex_bonus": True}}
    assert vitals.armor_class(_scores(dex=18), [("fighter", 5)], medium) == 16     # 14 + min(4, 2)


def test_unknown_class_index_does_not_crash(catalog):
    # derivation trusts validated input, but must degrade gracefully (default hit die) not AttributeError
    assert vitals.max_hp(catalog, [("nonexistent", 3)], 0) > 0
    assert vitals.hit_dice(catalog, [("nonexistent", 3)]) == {"d8": 3}


def test_speed(catalog):
    assert vitals.speed(catalog, "Human") == 30
    assert vitals.speed(catalog, "Highlander") == 35               # subrace sets its own speed
    assert vitals.speed(catalog, "Unknownfolk") == 30              # generic fallback
