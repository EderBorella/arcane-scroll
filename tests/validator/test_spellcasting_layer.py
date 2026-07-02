"""spellcasting layer: unified prepared model + real-spell membership; spell/pact slots vs the caster
classes; cantrip/prepared counts; no spell above the top slot level; subclass always-prepared grants.
Synthetic, content-neutral rules."""
from validator.checks import spellcasting
from validator.rules import Rules

R = Rules(spell_lists={"caster-a": {"Spell-A": 1, "Cantrip-A": 0}, "caster-b": {"Spell-B": 3}})


def _sheet(spells):
    return {"spellcasting": {"sources": {}, "spell_slots": {}, "spells": spells}}


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
    spell_lists={"mage": {"Bolt": 1, "Zap": 0, "Big": 3, "Huge": 5, "Arc": 6}},
    caster_types={"mage": "full", "knight": "half", "hexer": "pact", "scribe": "full"},
    class_progression={"mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}},
                       "knight": {"5": {"prepared_spells": 6}},
                       "scribe": {"5": {"cantrips_known": 4, "prepared_spells": 6}}},
    spell_slots={"classes": {"mage": {"5": {"1": 4, "2": 3, "3": 2}}, "knight": {"5": {"1": 2}},
                             "scribe": {"5": {"1": 4, "2": 3, "3": 2}}},
                 "multiclass": {"3": {"1": 4, "2": 2}, "4": {"1": 4, "2": 3},
                                "7": {"1": 4, "2": 3, "3": 3, "4": 1}},
                 "pact": {"5": {"slots": 2, "level": 3}, "17": {"slots": 4, "level": 5}}, "third": {}},
    subclass_spells={"order-x": {"3": ["Big"]}, "order-y": {"3": ["Offlist-Z"]}},
    caster_meta={"spellbook": ["scribe"], "arcanum": {"11": 6, "13": 7, "15": 8, "17": 9},
                 "always_prepared": {"knight": ["Smite-A"]}})


def _pool(t):
    """Wrap a flat {level: count} table into the contract's {level: {max, remaining}} pool shape."""
    return {k: {"max": v, "remaining": v} for k, v in (t or {}).items()}


def _csheet(classes, spells, spell_slots=None, pact_slots=None, sources=None):
    sc = {"sources": sources or {}, "spell_slots": _pool(spell_slots), "spells": spells}
    if pact_slots is not None:
        sc["pact_slots"] = _pool(pact_slots)
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


def test_half_caster_multiclass_rounds_up():
    # knight (half) level 5 → ceil(5/2)=3, + mage (full) 1 = combined 4 (NOT floor 2+1=3).
    classes = [{"class": "knight", "level": 5, "subclass": None},
               {"class": "mage", "level": 1, "subclass": None}]
    assert RC.expected_slots(classes) == {"1": 4, "2": 3}          # multiclass[4], not multiclass[3]


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


def test_spellbook_unprepared_leveled_ok():
    # 'scribe' is a spellbook caster: an unprepared leveled spell (spellbook entry) must NOT be flagged.
    spells = ([{"name": "Zap", "level": 0, "prepared": True}] * 4
              + [{"name": "Bolt", "level": 1, "prepared": True}] * 6
              + [{"name": "Big", "level": 3, "prepared": False}])          # spellbook, unprepared
    s = _csheet([{"class": "scribe", "level": 5, "subclass": None}], spells,
                spell_slots={"1": 4, "2": 3, "3": 2})
    assert "spell_not_prepared" not in _codes(s, RC)


def test_arcanum_allows_high_spell():
    # Warlock-like pact caster L17 with a level-6 spell cast via Mystic Arcanum (no matching slot).
    s = _csheet([{"class": "hexer", "level": 17, "subclass": None}],
                [{"name": "Arc", "level": 6, "prepared": True}], pact_slots={"5": 4})
    assert "spell_level_too_high" not in _codes(s, RC)


def test_no_arcanum_flags_high_spell():
    # Same spell at L5 (no arcanum yet) exceeds the level-3 pact slot → flagged.
    s = _csheet([{"class": "hexer", "level": 5, "subclass": None}],
                [{"name": "Arc", "level": 6, "prepared": True}], pact_slots={"3": 2})
    assert "spell_level_too_high" in _codes(s, RC)


def test_class_feature_always_prepared_not_counted():
    # 'Smite-A' is a class-feature always-prepared spell for 'knight' → excluded from the budget.
    spells = [{"name": "Bolt", "level": 1, "prepared": True}] * 6 + [{"name": "Smite-A", "level": 1, "prepared": True}]
    s = _csheet([{"class": "knight", "level": 5, "subclass": None}], spells, spell_slots={"1": 2})
    assert "prepared_count" not in _codes(s, RC)


def test_pool_slots_ignore_remaining():
    # spent slots (remaining < max) must NOT trip the rules check — only max is rule-checkable.
    s = _legal_mage()
    for pool in s["spellcasting"]["spell_slots"].values():
        pool["remaining"] = 0
    assert "spell_slots_mismatch" not in _codes(s, RC)


def test_pool_slots_wrong_max_triggers_mismatch():
    # pool-shaped (not int-compat) with a wrong max must still flag — pins the dict branch of _slot_maxes.
    s = _legal_mage()
    s["spellcasting"]["spell_slots"]["1"]["max"] = 2          # class grants 4 at level 1
    assert "spell_slots_mismatch" in _codes(s, RC)


def test_class_sourced_spell_still_counted():
    # a spell whose source kind is 'class' must NOT be excluded from the budget.
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"cls-x": {"kind": "class"}}
    s["spellcasting"]["spells"][0]["source"] = "cls-x"
    assert "cantrip_count" not in _codes(s, RC)


def test_unattributed_spell_still_counted():
    # a cantrip with no source is class-treated → an over-budget one still trips cantrip_count.
    s = _legal_mage()
    s["spellcasting"]["spells"].append({"name": "Zap", "level": 0, "prepared": True})   # 5th, budget is 4
    assert "cantrip_count" in _codes(s, RC)


def test_slotless_source_cantrip_not_counted():
    # a class mage (4 cantrips) plus a species-granted cantrip: the extra must not inflate the class
    # cantrip budget, and the off-list species cantrip must not be flagged unknown.
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"species-x": {"kind": "species", "cantrips_known": 1}}
    s["spellcasting"]["spells"].append({"name": "Species-Cantrip", "level": 0, "prepared": True,
                                        "source": "species-x"})
    codes = _codes(s, RC)
    assert "cantrip_count" not in codes and "unknown_spell" not in codes
    assert "source_cantrips_exceeded" not in codes             # 1 tagged ≤ declared 1


def test_source_over_attribution_flagged():
    # over-attribution loophole: 3 cantrips tagged to a species source that declares it grants 1.
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"species-x": {"kind": "species", "cantrips_known": 1}}
    for _ in range(3):
        s["spellcasting"]["spells"].append({"name": "Off-A", "level": 0, "prepared": True, "source": "species-x"})
    assert "source_cantrips_exceeded" in _codes(s, RC)


def test_source_undeclared_limit_not_bounded():
    # a source that declares no limit can't be bounded → no source_* violation (no false positive).
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"species-x": {"kind": "species"}}
    s["spellcasting"]["spells"].append({"name": "Off-A", "level": 0, "prepared": True, "source": "species-x"})
    codes = _codes(s, RC)
    assert "source_cantrips_exceeded" not in codes and "source_spells_exceeded" not in codes


def test_offlist_subclass_grant_is_known_and_normalised():
    # 'order-y' grants 'Offlist-Z' (not on any base list); it's folded into the known set, and the
    # present/prepared check is normalised (sheet uses lowercase).
    spells = ([{"name": "Zap", "level": 0, "prepared": True}] * 4
              + [{"name": "Bolt", "level": 1, "prepared": True}] * 6
              + [{"name": "offlist-z", "level": 2, "prepared": True}])
    s = _csheet([{"class": "mage", "level": 5, "subclass": "Order-Y"}], spells,
                spell_slots={"1": 4, "2": 3, "3": 2})
    codes = _codes(s, RC)
    assert "unknown_spell" not in codes and "subclass_spell_missing" not in codes
