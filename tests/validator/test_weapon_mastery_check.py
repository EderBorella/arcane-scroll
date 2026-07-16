import pytest

from validator.checks.weapon_mastery import check

_WM_FEATURE = [{"name": "Weapon Mastery", "source": "Class A 1"}]


def _sheet(masteries=None, features=None):
    """Build a sheet. ``masteries`` populates the top-level weapon_masteries field
    (omitted entirely when None). ``features`` defaults to a Weapon Mastery feature."""
    s = {
        "identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
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


def test_field_ignored_without_feature(access):
    # weapon_masteries populated but no Weapon Mastery feature -> not this check's concern
    s = _sheet(masteries=["fakename"], features=[{"name": "Spellcasting"}])
    assert check(s, access) == []


def test_case_insensitive_names(access):
    assert check(_sheet(masteries=["Weapon A", "Weapon C"]), access) == []


def test_case_insensitive_feature_name(access):
    s = _sheet(masteries=["weapon-a"], features=[{"name": "weapon mastery"}])
    assert check(s, access) == []


def test_mixed_valid_and_invalid(access):
    vs = check(_sheet(masteries=["weapon-a", "weapon-d"]), access)
    codes = {v.code for v in vs}
    assert "mastery-choice-invalid" in codes
    assert len([v for v in vs if v.code == "mastery-choice-invalid"]) == 1
