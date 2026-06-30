"""Ability scores: the modifier primitive, racial + ASI application, reserved-ASI rule, and caps."""
from app.derivation import abilities


def _classes(choices):
    return abilities.class_levels(choices)


def test_modifier():
    assert [abilities.modifier(s) for s in (8, 10, 14, 20)] == [-1, 0, 2, 5]


def test_ability_scores_apply_race_and_asi(catalog):
    choices = {"race": "Human", "feat": "Ability Score Improvement: Intelligence",
               "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10}}
    s = abilities.ability_scores(catalog, choices, _classes(choices))
    assert s["int"] == 18 and s["str"] == 8          # 15 + 1 racial + 2 ASI


def test_reserved_asi_allocated_smartly(catalog):
    # 2 feats + 3 slots → 1 reserved ASI (2 pts). Str 15 → 16 (not a wasted 17); the spare point evens
    # the next-highest odd ability (Dex 13 → 14) instead.
    choices = {"race": "Human", "feat": ["FeatA", "FeatB"],
               "classes": [{"class": "Fighter", "level": 8}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    s = abilities.ability_scores(catalog, choices, _classes(choices))
    assert s["str"] == 16 and s["dex"] == 14


def test_asi_pumps_even_primary_toward_20(catalog):
    # the main attribute climbs to 20 through odd steps (Str 16 + two ASI slots = 4 pts → 20)
    choices = {"race": "Human", "classes": [{"class": "Fighter", "level": 4}, {"class": "Rogue", "level": 4}],
               "ability_assignment": {"str": 16, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    assert abilities.ability_scores(catalog, choices, _classes(choices))["str"] == 20


def test_ability_scores_cap_at_20(catalog):
    choices = {"race": "Human", "feat": "Ability Score Improvement: Intelligence",
               "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 19, "wis": 12, "cha": 10}}
    assert abilities.ability_scores(catalog, choices, _classes(choices))["int"] == 20


def test_one_feat_slot_picking_a_feat_bumps_nothing(catalog):
    choices = {"race": "Human", "feat": "FeatA", "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10}}
    assert abilities.ability_scores(catalog, choices, _classes(choices))["int"] == 16   # racial only


def test_asi_named_ability_is_ignored(catalog):
    # the ability the model names on an ASI pick is ignored — the slot's 2 points are placed optimally
    choices = {"race": "Human", "feat": "Ability Score Improvement: Charisma",
               "classes": [{"class": "Fighter", "level": 4}],     # 1 ASI slot
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    s = abilities.ability_scores(catalog, choices, _classes(choices))
    assert s["str"] == 16 and s["dex"] == 14 and s["cha"] == 8    # not +2 Charisma


def test_multiclass_asi_slots_are_summed(catalog):
    choices = {"race": "Human", "classes": [{"class": "Fighter", "level": 4}, {"class": "Rogue", "level": 4}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    # 2 ASI slots → 4 pts: Str 15 → 18 (3 pts, kept even), spare evens Dex 13 → 14
    s = abilities.ability_scores(catalog, choices, _classes(choices))
    assert s["str"] == 18 and s["dex"] == 14
