import pytest

from validator.checks.weapon_mastery import check


def _sheet(features=None):
    return {
        "identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
        "features": features if features is not None else [],
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_valid_mastery_choices(access):
    s = _sheet(features=[{"name": "Weapon Mastery", "source": "Class A 1", "choices": ["greataxe", "handaxe"]}])
    assert check(s, access) == []


def test_invalid_weapon_name(access):
    s = _sheet(features=[{"name": "Weapon Mastery", "source": "Class A 1", "choices": ["greataxe", "fakename"]}])
    assert "mastery-choice-invalid" in _codes(s, access)


def test_weapon_without_mastery(access):
    s = _sheet(features=[{"name": "Weapon Mastery", "source": "Class A 1", "choices": ["net"]}])
    assert "mastery-choice-invalid" in _codes(s, access)


def test_empty_choices(access):
    s = _sheet(features=[{"name": "Weapon Mastery", "source": "Class A 1", "choices": []}])
    assert "mastery-choices-missing" in _codes(s, access)


def test_non_mastery_feature_ignored(access):
    s = _sheet(features=[{"name": "Fighting Style", "source": "Class A 1", "choices": ["StyleA"]}])
    assert check(s, access) == []


def test_multiple_mastery_features_multiclass(access):
    s = _sheet(features=[
        {"name": "Weapon Mastery", "source": "Class A 1", "choices": ["greataxe", "handaxe"]},
        {"name": "Weapon Mastery", "source": "Class B 1", "choices": ["club"]},
    ])
    assert check(s, access) == []


def test_case_insensitive_name(access):
    s = _sheet(features=[{"name": "weapon mastery", "source": "Class A 1", "choices": ["Greataxe", "Club"]}])
    assert check(s, access) == []


def test_no_weapon_mastery_feature(access):
    s = _sheet(features=[{"name": "Spellcasting", "source": "Class A 1"}])
    assert check(s, access) == []


def test_mixed_valid_and_invalid_choices(access):
    s = _sheet(features=[{"name": "Weapon Mastery", "source": "Class A 1", "choices": ["greataxe", "net"]}])
    vs = check(s, access)
    codes = {v.code for v in vs}
    assert "mastery-choice-invalid" in codes
    assert len([v for v in vs if v.code == "mastery-choice-invalid"]) == 1
