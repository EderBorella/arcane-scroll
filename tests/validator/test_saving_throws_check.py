from validator.checks.saving_throws import check


def _sheet(saving_throws=None, classes=None, proficiency_bonus=2, feats=None, species=None):
    ident = {"classes": classes if classes is not None else [{"class": "Class A", "level": 3}]}
    if species is not None:
        ident["species"] = species
    return {
        "identity": ident,
        "feats": feats if feats is not None else [],
        "abilities": {
            "x1": {"final": 15, "modifier": 2},
            "x2": {"final": 14, "modifier": 2},
            "x3": {"final": 13, "modifier": 1},
        },
        "proficiency_bonus": proficiency_bonus,
        "saving_throws": saving_throws if saving_throws is not None else {
            "x1": {"proficient": True, "modifier": 4},
            "x2": {"proficient": True, "modifier": 4},
            "x3": {"proficient": False, "modifier": 1},
        },
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_marking_a_non_class_save_proficient_is_a_mismatch(access):
    s = _sheet(saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 1},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


def test_wrong_modifier(access):
    s = _sheet(saving_throws={
        "x1": {"proficient": True, "modifier": 99},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": False, "modifier": 1},
    })
    assert "save-modifier-mismatch" in _codes(s, access)


def test_unmarking_a_class_save_proficient_is_a_mismatch(access):
    s = _sheet(saving_throws={
        "x1": {"proficient": False, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": False, "modifier": 1},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


def test_feat_granted_save_proficiency_is_legal(access):
    # feat-save (Resilient-like) grants proficiency in a3 (x3) via grant_proficiency -- a sheet
    # proficient in it while holding that feat is legal, even though a3 isn't a class-a save.
    s = _sheet(feats=["Feat Save"], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_save_proficiency_without_granting_feat_is_still_a_mismatch(access):
    # same a3-proficient sheet, but WITHOUT feat-save -- still illegal (real errors like g035
    # must still be caught).
    s = _sheet(feats=[], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)
