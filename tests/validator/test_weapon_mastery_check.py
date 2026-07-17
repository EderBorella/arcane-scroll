import pytest

from validator.checks.weapon_mastery import check

_WM_FEATURE = [{"name": "Weapon Mastery", "source": "Class A 1"}]


def _sheet(masteries=None, features=None):
    """Build a sheet. ``masteries`` populates the top-level weapon_masteries field
    (omitted entirely when None). ``features`` defaults to a Weapon Mastery feature.
    The default class (class-wm at level 1) confers an allowance of 2, so WHICH-picks
    tests that carry two entries are not perturbed by the count or entitlement checks."""
    s = {
        "identity": {"species": "Species A", "classes": [{"class": "class-wm", "level": 1}]},
        "features": _WM_FEATURE if features is None else features,
    }
    if masteries is not None:
        s["weapon_masteries"] = masteries
    return s


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_valid_mastery_choices(access):
    assert check(_sheet(masteries=["weapon-a", "weapon-b"]), access) == []


def test_invalid_weapon_name(access):
    assert "mastery-choice-invalid" in _codes(_sheet(masteries=["weapon-a", "fakename"]), access)


def test_weapon_without_mastery(access):
    assert "mastery-choice-invalid" in _codes(_sheet(masteries=["weapon-d"]), access)


def test_empty_masteries_with_feature(access):
    assert "mastery-choices-missing" in _codes(_sheet(masteries=[]), access)


def test_missing_field_with_feature(access):
    # feature present but no weapon_masteries field at all -> incomplete
    assert "mastery-choices-missing" in _codes(_sheet(masteries=None), access)


def test_no_weapon_mastery_feature_ignored(access):
    # a non-mastery feature and no field -> nothing to validate
    s = _sheet(masteries=None, features=[{"name": "Fighting Style", "source": "Class A 1"}])
    assert check(s, access) == []


def test_field_ignored_without_feature_when_entitled(access):
    # weapon_masteries populated and a class DOES confer an entitlement, but no Weapon Mastery
    # feature dict is present -> which/count validation is feature-gated, so nothing flags here.
    s = {
        "identity": {"species": "Species A", "classes": [{"class": "class-wm", "level": 1}]},
        "features": [{"name": "Spellcasting"}],
        "weapon_masteries": ["fakename"],
    }
    assert check(s, access) == []


def test_case_insensitive_names(access):
    assert check(_sheet(masteries=["Weapon A", "Weapon C"]), access) == []


def test_case_insensitive_feature_name(access):
    s = _sheet(masteries=["weapon-a", "weapon-b"], features=[{"name": "weapon mastery"}])
    assert check(s, access) == []


def test_mixed_valid_and_invalid(access):
    vs = check(_sheet(masteries=["weapon-a", "weapon-d"]), access)
    codes = {v.code for v in vs}
    assert "mastery-choice-invalid" in codes
    assert len([v for v in vs if v.code == "mastery-choice-invalid"]) == 1


# --- count check (T103): the number of picks vs the DB-derived allowance ---------------------------

def _wm_sheet(classes, masteries):
    """A sheet carrying the Weapon Mastery feature and the given classes ([(class, level), ...]) and
    weapon_masteries list."""
    return {
        "identity": {"species": "Species A",
                     "classes": [{"class": c, "level": lvl} for c, lvl in classes]},
        "features": _WM_FEATURE,
        "weapon_masteries": masteries,
    }


def test_count_matches_single_class_passes(access):
    # class-wm confers 2 at level 1; two valid picks -> no mismatch
    assert check(_wm_sheet([("class-wm", 1)], ["weapon-a", "weapon-b"]), access) == []


def test_count_too_few_flags(access):
    vs = check(_wm_sheet([("class-wm", 1)], ["weapon-a"]), access)
    m = [v for v in vs if v.code == "mastery-count-mismatch"]
    assert len(m) == 1 and m[0].kind == "incomplete"


def test_count_too_many_flags(access):
    vs = check(_wm_sheet([("class-wm", 1)], ["weapon-a", "weapon-b", "weapon-c"]), access)
    m = [v for v in vs if v.code == "mastery-count-mismatch"]
    assert len(m) == 1 and m[0].kind == "illegal"


def test_count_scales_with_class_level(access):
    # class-wm's ladder steps up to 3 at level 5
    assert check(_wm_sheet([("class-wm", 5)], ["weapon-a", "weapon-b", "weapon-c"]), access) == []
    assert "mastery-count-mismatch" in _codes(_wm_sheet([("class-wm", 5)], ["weapon-a", "weapon-b"]), access)


def test_multiclass_counts_stack_not_max(access):
    # class-wm (2 at lvl 1) + class-wm2 (1 at lvl 1): the STACKING rule gives 3, not the MAX of 2.
    assert check(_wm_sheet([("class-wm", 1), ("class-wm2", 1)],
                           ["weapon-a", "weapon-b", "weapon-c"]), access) == []
    # a sheet built to the (wrong) MAX rule of 2 is flagged as short by one
    vs = check(_wm_sheet([("class-wm", 1), ("class-wm2", 1)], ["weapon-a", "weapon-b"]), access)
    m = [v for v in vs if v.code == "mastery-count-mismatch"]
    assert len(m) == 1 and m[0].kind == "incomplete"


def test_count_capped_at_masterable_pool(access):
    # class-wm (3 at lvl 5) + class-wm2 (1 at lvl 1) sums to 4, but only 3 weapons carry a mastery
    # property, so the allowance caps at the pool size (3).
    assert check(_wm_sheet([("class-wm", 5), ("class-wm2", 1)],
                           ["weapon-a", "weapon-b", "weapon-c"]), access) == []


def test_no_entitlement_flags_with_feature(access):
    # class-a confers no weapon-mastery count: there is no allowance, so carrying masteries is an
    # illegal no-entitlement finding (not a count mismatch), even though the feature is present.
    vs = check(_wm_sheet([("class-a", 3)], ["weapon-a"]), access)
    codes = {v.code for v in vs}
    assert "mastery-not-entitled" in codes
    assert "mastery-count-mismatch" not in codes
    m = [v for v in vs if v.code == "mastery-not-entitled"]
    assert m[0].kind == "illegal"


def test_no_entitlement_flags_without_feature(access):
    # a build with no weapon-mastery-granting class and no Weapon Mastery feature may not carry
    # weapon_masteries at all -- carrying them anyway is an illegal no-entitlement finding.
    s = {
        "identity": {"species": "Species A", "classes": [{"class": "class-a", "level": 3}]},
        "features": [{"name": "Spellcasting"}],
        "weapon_masteries": ["weapon-a", "weapon-b"],
    }
    vs = check(s, access)
    m = [v for v in vs if v.code == "mastery-not-entitled"]
    assert len(m) == 1 and m[0].kind == "illegal"


def test_no_entitlement_not_flagged_when_empty(access):
    # a no-entitlement build with an empty (or absent) weapon_masteries list is fine.
    s = {
        "identity": {"species": "Species A", "classes": [{"class": "class-a", "level": 3}]},
        "features": [{"name": "Spellcasting"}],
        "weapon_masteries": [],
    }
    assert check(s, access) == []
