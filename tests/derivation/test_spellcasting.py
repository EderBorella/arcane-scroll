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
