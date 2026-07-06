import sqlite3

import pytest

from validator.checks.vitals import check


@pytest.fixture
def access(rules_db):
    """Vitals needs a sheet ability resolvable via the real-DB constitution abbrev 'con'. The shared
    synthetic ability table (built for the abilities/saving_throws domains) only carries the
    x1..x6 synthetic abbrevs, so alias a3 (x3) to 'con' in this test file's own private copy of the
    rules DB — this doesn't affect any other test file, since rules_db is rebuilt fresh per test."""
    con = sqlite3.connect(rules_db)
    con.execute("UPDATE ability SET abbrev='con' WHERE id='a3'")
    con.commit()
    con.close()
    from access.validator import ValidatorAccess
    return ValidatorAccess(path=rules_db)


def _sheet(classes=None, hit_dice=None, hp_max=22, con_final=14, species="Species A"):
    classes = classes if classes is not None else [{"class": "Class A", "level": 3}]
    total_level = sum(c["level"] for c in classes)
    con_mod = (con_final - 10) // 2
    return {
        "identity": {"species": species, "classes": classes, "total_level": total_level},
        "abilities": {"con": {"final": con_final, "modifier": con_mod}},
        "combat": {
            "hit_points": {"max": hp_max},
            "hit_dice": hit_dice if hit_dice is not None else {"d8": {"max": total_level, "remaining": total_level}},
        },
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_hit_dice_total_mismatch(access):
    s = _sheet(hit_dice={"d8": {"max": 2, "remaining": 2}})
    assert "hit-dice-total-mismatch" in _codes(s, access)


def test_hit_dice_face_invalid(access):
    s = _sheet(hit_dice={"d8": {"max": 3, "remaining": 3}, "d10": {"max": 0, "remaining": 0}})
    assert "hit-dice-face-invalid" in _codes(s, access)


def test_hp_out_of_range(access):
    s = _sheet(hp_max=999)
    assert "hp-out-of-range" in _codes(s, access)


def test_multiclass_hit_dice_pool_is_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2}, {"class": "Class B", "level": 1}],
               hit_dice={"d8": {"max": 2, "remaining": 2}, "d10": {"max": 1, "remaining": 1}},
               hp_max=26)
    assert check(s, access) == []
