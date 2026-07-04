"""spellcasting layer (v6): per-source counting on the bucket model. Each spell names its `source` (a key
in spellcasting.sources) and a `bucket` (cantrip|prepared|always|known); cantrip/prepared count against
that source's budget, always/known are additive. (name, source) is unique. Every spell is a catalog
member. Slot/pact/level/S17 checks preserved. Synthetic, content-neutral rules.

NOTE (Increment 2, not yet covered here): bucket↔recovery coupling, `always`-grant-spec validation
(fixed vs choose{from}), per-pick class-list constraint-checking, secondary_cast, known-uncastable."""
from validator.checks import spellcasting
from validator.rules import Rules
from validator.report import ERROR

MAGE_CANTRIPS = ["Zap", "Flare", "Spark", "Glow"]          # 4, level 0, mage
MAGE_LEVELED = ["Bolt", "Dart", "Ward", "Mend", "Guard", "Web"]   # 6, level 1, mage
SCRIBE_CANTRIPS = ["Ping", "Pong", "Ding", "Dong"]         # 4, level 0, scribe
SCRIBE_LEVELED = ["Beam", "Ray", "Gild", "Sear", "Numb", "Bind"]  # 6, level 1, scribe


def _cat(name, level, classes, school=None):
    return {"id": name.lower(), "name": name, "level": level, "classes": classes, "school": school}


RC = Rules(
    spells=([_cat(n, 0, ["mage"]) for n in MAGE_CANTRIPS + ["Shimmer"]]
            + [_cat(n, 1, ["mage"]) for n in MAGE_LEVELED]
            + [_cat(n, 0, ["scribe"]) for n in SCRIBE_CANTRIPS]
            + [_cat(n, 1, ["scribe"]) for n in SCRIBE_LEVELED]
            + [_cat("Big", 3, ["mage"]), _cat("Huge", 5, ["mage"]),
               _cat("Arc", 6, ["hexer"]), _cat("Hex", 1, ["hexer"]), _cat("Smite-A", 1, ["knight"])]),
    caster_types={"mage": "full", "knight": "half", "hexer": "pact", "scribe": "full"},
    class_progression={"mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}},
                       "knight": {"5": {"prepared_spells": 6}},
                       "scribe": {"5": {"cantrips_known": 4, "prepared_spells": 6}}},
    spell_slots={"classes": {"mage": {"5": {"1": 4, "2": 3, "3": 2}}, "knight": {"5": {"1": 2}},
                             "scribe": {"5": {"1": 4, "2": 3, "3": 2}}},
                 "multiclass": {"4": {"1": 4, "2": 3}, "7": {"1": 4, "2": 3, "3": 3, "4": 1},
                                "10": {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2}},
                 "pact": {"5": {"slots": 2, "level": 3}, "17": {"slots": 4, "level": 5}}, "third": {}},
    caster_meta={"arcanum": {"11": 6, "13": 7, "15": 8, "17": 9}})


def _pool(t):
    return {k: {"max": v, "remaining": v} for k, v in (t or {}).items()}


def _csheet(classes, spells, spell_slots=None, pact_slots=None, sources=None):
    sc = {"sources": sources or {}, "spell_slots": _pool(spell_slots), "spells": spells}
    if pact_slots is not None:
        sc["pact_slots"] = _pool(pact_slots)
    return {"identity": {"classes": classes}, "spellcasting": sc}


def _codes(sheet, rules=RC):
    return {v.code for v in spellcasting.check(sheet, rules)}


def _sp(name, level, bucket, source, **kw):
    return {"name": name, "level": level, "bucket": bucket, "source": source, **kw}


def _spells_for(cantrips, leveled, source):
    return ([_sp(n, 0, "cantrip", source) for n in cantrips]
            + [_sp(n, 1, "prepared", source) for n in leveled])


def _legal_mage():
    return _csheet([{"class": "mage", "level": 5, "subclass": None}],
                   _spells_for(MAGE_CANTRIPS, MAGE_LEVELED, "mage"),
                   spell_slots={"1": 4, "2": 3, "3": 2}, sources={"mage": {"kind": "class"}})


def test_no_spellcasting_block_is_fine():
    assert spellcasting.check({"spellcasting": None}, RC) == []


def test_single_class_fully_legal():
    assert spellcasting.check(_legal_mage(), RC) == []


def test_cantrip_count_per_source():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Shimmer", 0, "cantrip", "mage"))   # 5th, budget 4
    assert "cantrip_count" in _codes(s)


def test_prepared_count_per_source():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Big", 3, "prepared", "mage"))      # 7th, budget 6
    assert "prepared_count" in _codes(s)


def test_always_bucket_not_counted():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Big", 3, "always", "mage"))        # additive grant
    assert "prepared_count" not in _codes(s)


def test_known_bucket_not_counted():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Big", 3, "known", "mage"))         # spellbook, unprepared
    assert "prepared_count" not in _codes(s)


def test_multiclass_counts_exact_and_legal():
    # mage5 (full) + scribe5 (full) → combined 10; each source counted independently → EXACT, legal.
    spells = _spells_for(MAGE_CANTRIPS, MAGE_LEVELED, "mage") + _spells_for(SCRIBE_CANTRIPS, SCRIBE_LEVELED, "scribe")
    s = _csheet([{"class": "mage", "level": 5, "subclass": None}, {"class": "scribe", "level": 5, "subclass": None}],
                spells, spell_slots={"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
                sources={"mage": {"kind": "class"}, "scribe": {"kind": "class"}})
    assert spellcasting.check(s, RC) == []


def test_multiclass_one_source_off_is_hard_error():
    # scribe has 3 cantrips not 4 → ERROR (no advisory downgrade), because attribution is exact.
    spells = _spells_for(MAGE_CANTRIPS, MAGE_LEVELED, "mage") + _spells_for(SCRIBE_CANTRIPS[:3], SCRIBE_LEVELED, "scribe")
    s = _csheet([{"class": "mage", "level": 5, "subclass": None}, {"class": "scribe", "level": 5, "subclass": None}],
                spells, spell_slots={"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
                sources={"mage": {"kind": "class"}, "scribe": {"kind": "class"}})
    assert ("cantrip_count", ERROR) in {(v.code, v.severity) for v in spellcasting.check(s, RC)}


def test_duplicate_name_source_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Bolt", 1, "prepared", "mage"))   # (Bolt, mage) already present
    assert "duplicate_spell" in _codes(s)


def test_same_name_different_source_ok():
    s = _legal_mage()
    s["spellcasting"]["sources"]["knight"] = {"kind": "class"}
    s["spellcasting"]["spells"].append(_sp("Bolt", 1, "always", "knight"))   # same name, different source
    assert "duplicate_spell" not in _codes(s)


def test_unknown_source_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"][0]["source"] = "ghost"
    assert "unknown_source" in _codes(s)


def test_unknown_spell_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Nope", 1, "always", "mage"))
    assert "unknown_spell" in _codes(s)


def test_membership_skipped_without_catalog():
    empty = Rules(class_progression={"mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}}},
                  caster_types={"mage": "full"})
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Whatever", 1, "always", "mage"))
    assert "unknown_spell" not in _codes(s, empty)


def test_spell_slots_mismatch():
    s = _legal_mage()
    s["spellcasting"]["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
    assert "spell_slots_mismatch" in _codes(s)


def test_pool_slots_ignore_remaining():
    s = _legal_mage()
    for pool in s["spellcasting"]["spell_slots"].values():
        pool["remaining"] = 0
    assert "spell_slots_mismatch" not in _codes(s)


def test_pact_slots_ok_and_mismatch():
    base = _csheet([{"class": "hexer", "level": 5, "subclass": None}], [_sp("Hex", 1, "always", "hexer")],
                   pact_slots={"3": 2}, sources={"hexer": {"kind": "class"}})
    assert "pact_slots_mismatch" not in _codes(base)
    base["spellcasting"]["pact_slots"] = {"2": {"max": 2, "remaining": 2}}
    assert "pact_slots_mismatch" in _codes(base)


def test_arcanum_allows_high_spell():
    s = _csheet([{"class": "hexer", "level": 17, "subclass": None}], [_sp("Arc", 6, "always", "hexer")],
                pact_slots={"5": 4}, sources={"hexer": {"kind": "class"}})
    assert "spell_level_too_high" not in _codes(s)


def test_no_arcanum_flags_high_spell():
    s = _csheet([{"class": "hexer", "level": 5, "subclass": None}], [_sp("Arc", 6, "always", "hexer")],
                pact_slots={"3": 2}, sources={"hexer": {"kind": "class"}})
    assert "spell_level_too_high" in _codes(s)


def test_declared_cantrips_known_wrong():
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"mage": {"kind": "class", "cantrips_known": 3, "prepared_limit": 6}}
    assert "cantrips_known_mismatch" in _codes(s)


def test_declared_prepared_limit_wrong():
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"mage": {"kind": "class", "cantrips_known": 4, "prepared_limit": 5}}
    assert "prepared_limit_mismatch" in _codes(s)


def test_declared_budgets_correct_ok():
    s = _legal_mage()
    s["spellcasting"]["sources"] = {"mage": {"kind": "class", "cantrips_known": 4, "prepared_limit": 6}}
    codes = _codes(s)
    assert "cantrips_known_mismatch" not in codes and "prepared_limit_mismatch" not in codes


# --- Increment 2, slice B: per-pick class-list constraint-checking --------------------------------

def test_class_pick_not_on_class_list_flagged():
    # 'Beam' is scribe-only; a mage preparing it is off-list.
    s = _legal_mage()
    s["spellcasting"]["spells"][4] = _sp("Beam", 1, "prepared", "mage")
    assert "spell_not_on_class_list" in _codes(s)


def test_class_pick_on_list_ok():
    assert "spell_not_on_class_list" not in _codes(_legal_mage())


def test_always_grant_exempt_from_class_list():
    # an 'always' grant from a subclass may sit off the class list — not flagged by the class-list check.
    s = _legal_mage()
    s["spellcasting"]["sources"]["order-a"] = {"kind": "subclass"}
    s["spellcasting"]["spells"].append(_sp("Beam", 1, "always", "order-a"))
    assert "spell_not_on_class_list" not in _codes(s)


def test_off_list_check_skipped_without_catalog():
    empty = Rules(class_progression={"mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}}},
                  caster_types={"mage": "full"})
    s = _legal_mage()
    s["spellcasting"]["spells"][4] = _sp("Beam", 1, "prepared", "mage")
    assert "spell_not_on_class_list" not in _codes(s, empty)


# --- Increment 2, slice C: `always`-grant-spec validation -----------------------------------------
# A grants-bearing fixture (synthetic, content-neutral): a fixed-grant subclass + a fixed+choose feat,
# with synthetic spell schools (school-a..e).

RG = Rules(
    spells=[_cat("Alfa", 1, ["priest"], "school-a"), _cat("Bravo", 1, ["priest"], "school-b"),
            _cat("Charlie", 2, ["mage"], "school-c"), _cat("Delta", 1, ["scribe", "mage"], "school-a"),
            _cat("Echo", 1, ["mage"], "school-d"), _cat("Foxtrot", 3, ["mage"], "school-e")],
    caster_types={"priest": "full", "mage": "full"},
    class_progression={"priest": {"3": {"cantrips_known": 3, "prepared_spells": 6}},
                       "mage": {"5": {"cantrips_known": 4, "prepared_spells": 6}}},
    grants={
        "order-a": {"kind": "subclass", "grants": [
            {"gained_at": {"scope": "class_level", "level": 3}, "bucket": "always",
             "spec": {"fixed": ["Alfa", "Bravo"], "choose": None}}]},
        "feat-a": {"kind": "feat", "grants": [
            {"gained_at": {"scope": "character_level", "level": 4}, "bucket": "always",
             "spec": {"fixed": ["Charlie"], "choose": None}},
            {"gained_at": {"scope": "character_level", "level": 4}, "bucket": "always",
             "spec": {"fixed": None, "choose": {"n": 1, "from": {"type": "school",
                                                                 "value": ["school-d", "school-a"],
                                                                 "spell_level": 1}}}}]}})


def _cs(classes, spells, sources):
    return {"identity": {"classes": classes},
            "spellcasting": {"sources": sources, "spell_slots": {}, "spells": spells}}


def test_always_fixed_grant_ok():
    s = _cs([{"class": "priest", "level": 3, "subclass": "Order A"}], [_sp("Alfa", 1, "always", "order-a")],
            {"priest": {"kind": "class"}, "order-a": {"kind": "subclass"}})
    assert "always_spell_not_granted" not in _codes(s, RG)


def test_always_not_granted_flagged():
    s = _cs([{"class": "priest", "level": 3, "subclass": "Order A"}], [_sp("Foxtrot", 3, "always", "order-a")],
            {"priest": {"kind": "class"}, "order-a": {"kind": "subclass"}})
    assert "always_spell_not_granted" in _codes(s, RG)


def test_always_choose_constraint_satisfied_ok():
    # feat-a: Charlie (fixed) + a chosen level-1 school-a/school-d spell. Delta (school-a, L1) satisfies.
    s = _cs([{"class": "mage", "level": 5, "subclass": None}],
            [_sp("Charlie", 2, "always", "feat-a"), _sp("Delta", 1, "always", "feat-a")],
            {"mage": {"kind": "class"}, "feat-a": {"kind": "feat"}})
    assert "always_spell_not_granted" not in _codes(s, RG)


def test_always_choose_constraint_violated_flagged():
    # Foxtrot (school-e, L3) fails feat-a's school-a/school-d level-1 constraint.
    s = _cs([{"class": "mage", "level": 5, "subclass": None}],
            [_sp("Charlie", 2, "always", "feat-a"), _sp("Foxtrot", 3, "always", "feat-a")],
            {"mage": {"kind": "class"}, "feat-a": {"kind": "feat"}})
    assert "always_spell_not_granted" in _codes(s, RG)


def test_always_from_ungranted_source_skipped():
    # 'mage' has no grant record → can't validate → no false positive.
    s = _cs([{"class": "mage", "level": 5, "subclass": None}], [_sp("Foxtrot", 3, "always", "mage")],
            {"mage": {"kind": "class"}})
    assert "always_spell_not_granted" not in _codes(s, RG)


# --- Increment 2, slice A: bucket ↔ recovery coupling ---------------------------------------------

def test_cantrip_with_slot_recovery_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"][0]["recovery"] = "spell_slot"          # a chosen cantrip is at-will, not slot-cast
    assert "bucket_recovery_mismatch" in _codes(s)


def test_prepared_with_at_will_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"][4]["recovery"] = "at_will"             # a prepared leveled spell isn't at-will
    assert "bucket_recovery_mismatch" in _codes(s)


def test_known_with_recovery_flagged():
    s = _legal_mage()
    s["spellcasting"]["spells"].append(_sp("Big", 3, "known", "mage", recovery="at_will"))  # unprepared → uncastable
    assert "bucket_recovery_mismatch" in _codes(s)


def test_legal_mage_no_coupling_issue():
    assert "bucket_recovery_mismatch" not in _codes(_legal_mage())


# --- Increment 2, slice D: repeatable-feat instance resolution ------------------------------------
# `feat-c_warden` is an INSTANCE of the repeatable feat `feat-c`; the `warden` variant narrows its
# choose{from: list} to the `warden` list specifically.

RGI = Rules(
    spells=[_cat("Golf", 1, ["warden"], "school-c"), _cat("Alfa", 1, ["priest"], "school-a")],
    grants={"feat-c": {"kind": "feat", "grants": [
        {"gained_at": {"scope": "character_level", "level": 1}, "bucket": "always",
         "spec": {"fixed": None, "choose": {"n": 1, "from": {"type": "list",
                                                             "value": ["priest", "warden", "mage"],
                                                             "spell_level": 1}}}}]}})


def test_repeatable_feat_instance_variant_ok():
    # Golf (warden list, L1) satisfies feat-c_warden.
    s = _cs([{"class": "mage", "level": 5, "subclass": None}], [_sp("Golf", 1, "always", "feat-c_warden")],
            {"mage": {"kind": "class"}, "feat-c_warden": {"kind": "feat"}})
    assert "always_spell_not_granted" not in _codes(s, RGI)


def test_repeatable_feat_instance_wrong_list_flagged():
    # Alfa is priest-only; the `warden` variant narrows the constraint to the warden list, so it fails.
    s = _cs([{"class": "priest", "level": 3, "subclass": None}], [_sp("Alfa", 1, "always", "feat-c_warden")],
            {"priest": {"kind": "class"}, "feat-c_warden": {"kind": "feat"}})
    assert "always_spell_not_granted" in _codes(s, RGI)


# --- Increment 2, slice E: grant level-gating + count validation ----------------------------------

RGS = Rules(
    spells=[_cat("Alfa", 1, ["priest"], "school-a"), _cat("Hotel", 2, ["priest"], "school-b"),
            _cat("India", 3, ["priest"], "school-c"), _cat("Golf", 1, ["warden"], "school-c"),
            _cat("Echo", 1, ["mage"], "school-d"), _cat("Juliet", 1, ["mage"], "school-d"),
            _cat("Kilo", 1, ["mage"], "school-d")],
    caster_types={"priest": "full", "mage": "full", "warden": "full"},
    class_progression={c: {str(l): {"proficiency_bonus": (2 if l < 5 else 3)} for l in range(1, 21)}
                       for c in ("priest", "mage", "warden")},
    grants={
        "order-a": {"kind": "subclass", "parent_class": "priest", "grants": [
            {"gained_at": {"scope": "class_level", "level": 3}, "bucket": "always",
             "spec": {"fixed": ["Alfa", "Hotel"], "choose": None}},
            {"gained_at": {"scope": "class_level", "level": 5}, "bucket": "always",
             "spec": {"fixed": ["India"], "choose": None}}]},
        "feat-b": {"kind": "feat", "grants": [
            {"gained_at": {"scope": "character_level", "level": 4}, "bucket": "always",
             "spec": {"fixed": None, "choose": {"n": "proficiency_bonus",
                                                "from": {"type": "school", "value": ["school-d"], "spell_level": 1}}}}]},
        "order-b": {"kind": "subclass", "parent_class": "warden", "grants": [
            {"gained_at": {"scope": "class_level", "level": 3}, "bucket": "always",
             "spec": {"fixed": None, "choose": {"n": "all_from_chosen_land", "from": {"type": "list", "value": ["warden"]}}}}]}})


def _order_a(level, spells):
    return _cs([{"class": "priest", "level": level, "subclass": "Order A"}], spells,
               {"priest": {"kind": "class"}, "order-a": {"kind": "subclass"}})


def test_grant_above_level_flagged():
    # India unlocks at class level 5; a level-3 priest can't have it yet.
    s = _order_a(3, [_sp("Alfa", 1, "always", "order-a"), _sp("Hotel", 2, "always", "order-a"),
                     _sp("India", 3, "always", "order-a")])
    assert "always_spell_not_granted" in _codes(s, RGS)


def test_grant_at_level_ok():
    s = _order_a(5, [_sp("Alfa", 1, "always", "order-a"), _sp("Hotel", 2, "always", "order-a"),
                     _sp("India", 3, "always", "order-a")])
    assert "always_spell_not_granted" not in _codes(s, RGS)


def test_grant_undercount_flagged():
    s = _order_a(3, [_sp("Alfa", 1, "always", "order-a")])             # grants 2 (Alfa+Hotel), only 1 listed
    assert "grant_count_mismatch" in _codes(s, RGS)


def test_grant_exact_count_ok():
    s = _order_a(3, [_sp("Alfa", 1, "always", "order-a"), _sp("Hotel", 2, "always", "order-a")])
    assert "grant_count_mismatch" not in _codes(s, RGS)


def test_pb_scaled_count_ok():
    # feat-b grants PB spells; mage level 5 → PB 3 → exactly 3 always level-1 school-d spells.
    s = _cs([{"class": "mage", "level": 5, "subclass": None}],
            [_sp("Echo", 1, "always", "feat-b"), _sp("Juliet", 1, "always", "feat-b"),
             _sp("Kilo", 1, "always", "feat-b")],
            {"mage": {"kind": "class"}, "feat-b": {"kind": "feat"}})
    assert "grant_count_mismatch" not in _codes(s, RGS)


def test_unresolvable_scaling_count_skipped():
    # order-b uses 'all_from_chosen_land' → count not resolvable → no false positive.
    s = _cs([{"class": "warden", "level": 3, "subclass": "Order B"}],
            [_sp("Golf", 1, "always", "order-b")],
            {"warden": {"kind": "class"}, "order-b": {"kind": "subclass"}})
    assert "grant_count_mismatch" not in _codes(s, RGS)
