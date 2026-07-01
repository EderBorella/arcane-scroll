"""spellcasting layer (2024): leveled spells must be prepared (unified model); every spell must be a
real 2024 spell. Synthetic, content-neutral rules."""
from validator.checks import spellcasting
from validator.rules import Rules

R = Rules(spell_lists={"caster-a": {"Spell-A": 1, "Cantrip-A": 0}, "caster-b": {"Spell-B": 3}})


def _sheet(spells):
    return {"spellcasting": {"classes": {}, "spell_slots": {}, "spells": spells}}


def _codes(sheet):
    return {v.code for v in spellcasting.check(sheet, R)}


def test_leveled_spell_must_be_prepared():
    assert "spell_not_prepared" in _codes(_sheet([{"name": "Spell-A", "level": 1, "prepared": False}]))


def test_prepared_leveled_ok_and_cantrip_ignored():
    s = _sheet([{"name": "Spell-A", "level": 1, "prepared": True},
                {"name": "Cantrip-A", "level": 0, "prepared": False}])
    assert spellcasting.check(s, R) == []


def test_unknown_spell_flagged():
    assert "unknown_spell" in _codes(_sheet([{"name": "Spell-Z", "level": 1, "prepared": True}]))


def test_no_spellcasting_block_is_fine():
    assert spellcasting.check({"spellcasting": None}, R) == []


def test_membership_skipped_without_data():
    # no spell-list data → the membership check must NOT fire (no false positives)
    empty = Rules()
    codes = {v.code for v in spellcasting.check(_sheet([{"name": "Anything", "level": 1, "prepared": True}]), empty)}
    assert "unknown_spell" not in codes
