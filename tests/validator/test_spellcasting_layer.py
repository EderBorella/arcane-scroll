"""spellcasting layer: unified prepared model + real-spell membership; spell/pact slots vs the caster
classes; cantrip/prepared counts; no spell above the top slot level; subclass always-prepared grants.
Synthetic, content-neutral rules."""
from validator.checks import spellcasting
from validator.rules import Rules

R = Rules(spell_lists={"caster-a": {"Spell-A": 1, "Cantrip-A": 0}, "caster-b": {"Spell-B": 3}})


def _sheet(spells):
    return {"spellcasting": {"classes": {}, "spell_slots": {}, "spells": spells}}


def _codes(sheet, rules=R):
    return {v.code for v in spellcasting.check(sheet, rules)}


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
    assert "unknown_spell" not in _codes(_sheet([{"name": "Anything", "level": 1, "prepared": True}]), empty)


# --- slots / counts / level / subclass grants -----------------------------------------------------

RC = Rules(
    spell_lists={"mage": {"Bolt": 1, "Zap": 0, "Big": 3, "Huge": 5}},
    caster_types={"mage": "full", "knight": "half", "hexer": "pact"},
    class_progression={"mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}},
                       "knight": {"5": {"prepared_spells": 6}}},
    spell_slots={"classes": {"mage": {"5": {"1": 4, "2": 3, "3": 2}}},
                 "multiclass": {"7": {"1": 4, "2": 3, "3": 3, "4": 1}},
                 "pact": {"5": {"slots": 2, "level": 3}}, "third": {}},
    subclass_spells={"order-x": {"3": ["Big"]}})


def _csheet(classes, spells, spell_slots=None, pact_slots=None):
    sc = {"classes": {}, "spell_slots": spell_slots or {}, "spells": spells}
    if pact_slots is not None:
        sc["pact_slots"] = pact_slots
    return {"identity": {"classes": classes}, "spellcasting": sc}


def _legal_mage():
    """A fully-legal single-class mage L5: 4 cantrips, 6 prepared, correct slots."""
    spells = ([{"name": "Zap", "level": 0, "prepared": True}] * 4
              + [{"name": "Bolt", "level": 1, "prepared": True}] * 6)
    return _csheet([{"class": "mage", "level": 5, "subclass": None}], spells,
                   spell_slots={"1": 4, "2": 3, "3": 2})


def test_single_class_fully_legal():
    assert spellcasting.check(_legal_mage(), RC) == []


def test_spell_slots_mismatch():
    s = _legal_mage()
    s["spellcasting"]["spell_slots"] = {"1": 2}
    assert "spell_slots_mismatch" in _codes(s, RC)


def test_pact_slots_ok_and_mismatch():
    base = _csheet([{"class": "hexer", "level": 5, "subclass": None}],
                   [{"name": "Bolt", "level": 1, "prepared": True}], pact_slots={"3": 2})
    assert "pact_slots_mismatch" not in _codes(base, RC)
    base["spellcasting"]["pact_slots"] = {"2": 2}
    assert "pact_slots_mismatch" in _codes(base, RC)


def test_cantrip_count():
    s = _legal_mage()
    s["spellcasting"]["spells"] = [x for x in s["spellcasting"]["spells"] if x["level"] != 0][:6]  # 0 cantrips
    assert "cantrip_count" in _codes(s, RC)


def test_prepared_count():
    s = _legal_mage()
    s["spellcasting"]["spells"].append({"name": "Bolt", "level": 1, "prepared": True})  # 7, needs 6
    assert "prepared_count" in _codes(s, RC)


def test_spell_level_too_high():
    s = _legal_mage()
    s["spellcasting"]["spells"].append({"name": "Huge", "level": 5, "prepared": True})  # top slot is 3
    assert "spell_level_too_high" in _codes(s, RC)


def test_subclass_grant_missing():
    s = _csheet([{"class": "mage", "level": 5, "subclass": "Order-X"}],
                [{"name": "Zap", "level": 0, "prepared": True}] * 4
                + [{"name": "Bolt", "level": 1, "prepared": True}] * 6)   # 'Big' (granted) absent
    assert "subclass_spell_missing" in _codes(s, RC)


def test_subclass_grant_present_not_double_counted():
    # 'Big' is granted → present + prepared, but must NOT count toward the 6 prepared budget.
    spells = ([{"name": "Zap", "level": 0, "prepared": True}] * 4
              + [{"name": "Bolt", "level": 1, "prepared": True}] * 6
              + [{"name": "Big", "level": 3, "prepared": True}])
    s = _csheet([{"class": "mage", "level": 5, "subclass": "Order-X"}], spells,
                spell_slots={"1": 4, "2": 3, "3": 2})
    codes = _codes(s, RC)
    assert "subclass_spell_missing" not in codes and "prepared_count" not in codes
