"""Subclass always-prepared grants (cleric domain / paladin oath) injected into the spellbook."""
from app.derivation import spellcasting


def test_grants_are_always_prepared_and_additive(catalog):
    choices = {"classes": [{"class": "Oracle", "level": 3, "subclass": "Seer"}],
               "spell_choices": {"cantrips": ["Spark"], "spells": ["Ward"]}}
    book = {s["name"]: s for s in spellcasting.spellbook(catalog, choices)}
    for nm in ("Bolt", "Quake", "Gale"):          # granted by the Seer table at L1 / L3
        assert book[nm]["prepared"] is True
    assert "Ward" in book                         # a chosen spell is not displaced by the grants


def test_grants_gated_by_class_level(catalog):
    choices = {"classes": [{"class": "Oracle", "level": 1, "subclass": "Seer"}], "spell_choices": {}}
    names = {s["name"] for s in spellcasting.spellbook(catalog, choices)}
    assert "Bolt" in names and "Quake" not in names   # only the L1 grant at level 1


def test_no_subclass_no_grants(catalog):
    choices = {"classes": [{"class": "Oracle", "level": 3}], "spell_choices": {}}
    assert spellcasting.spellbook(catalog, choices) == []


def test_land_circle_grants_by_land_type(catalog):
    choices = {"classes": [{"class": "Oracle", "level": 3, "subclass": "Landwarden"}],
               "land_type": "LandA", "spell_choices": {}}
    book = {s["name"]: s for s in spellcasting.spellbook(catalog, choices)}
    assert book["Bolt"]["prepared"] is True and book["Quake"]["prepared"] is True


def test_land_grants_gated_by_level_and_type(catalog):
    c1 = {"classes": [{"class": "Oracle", "level": 1, "subclass": "Landwarden"}],
          "land_type": "LandA", "spell_choices": {}}
    n1 = {s["name"] for s in spellcasting.spellbook(catalog, c1)}
    assert "Bolt" in n1 and "Quake" not in n1                 # level gates the L3 grant out at L1
    c2 = {"classes": [{"class": "Oracle", "level": 3, "subclass": "Landwarden"}],
          "land_type": "LandB", "spell_choices": {}}
    assert spellcasting.spellbook(catalog, c2) == []          # a land with no table → no grants
