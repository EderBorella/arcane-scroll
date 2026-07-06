from validator.checks.abilities import check


def _clean_abilities():
    return {
        "x1": {"base": 13, "background_bonus": 2, "final": 15, "modifier": 2},
        "x2": {"base": 13, "background_bonus": 1, "final": 14, "modifier": 2},
        "x3": {"base": 13, "final": 13, "modifier": 1},
        "x4": {"base": 13, "final": 13, "modifier": 1},
        "x5": {"base": 13, "final": 13, "modifier": 1},
        "x6": {"base": 13, "final": 13, "modifier": 1},
    }


def _sheet(abilities=None, background="Background A"):
    return {
        "identity": {"background": background},
        "abilities": _clean_abilities() if abilities is None else abilities,
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_wrong_modifier(access):
    abilities = _clean_abilities()
    abilities["x3"]["modifier"] = 5
    assert "modifier-mismatch" in _codes(_sheet(abilities), access)


def test_final_over_cap(access):
    abilities = _clean_abilities()
    abilities["x4"]["final"] = 21
    abilities["x4"]["modifier"] = 5
    assert "ability-over-cap" in _codes(_sheet(abilities), access)


def test_missing_ability(access):
    abilities = _clean_abilities()
    del abilities["x6"]
    assert "missing-ability" in _codes(_sheet(abilities), access)


def test_background_boost_on_disallowed_ability(access):
    abilities = _clean_abilities()
    # x4 (a4) is not one of bg-a's boostable abilities (a1, a2, a3)
    del abilities["x2"]["background_bonus"]
    abilities["x4"]["background_bonus"] = 1
    assert "background-boost-illegal" in _codes(_sheet(abilities), access)


def test_background_boost_wrong_sum(access):
    abilities = _clean_abilities()
    abilities["x1"]["background_bonus"] = 3
    abilities["x2"]["background_bonus"] = 1
    assert "background-boost-illegal" in _codes(_sheet(abilities), access)


def test_malformed_abilities_not_a_dict(access):
    assert "malformed-abilities" in _codes(_sheet(abilities="x"), access)
