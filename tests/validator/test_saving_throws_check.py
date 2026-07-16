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


def test_feat_granted_save_proficiency_as_object_entry_is_legal(access):
    # A top-level-fields sheet carries each feat as an OBJECT with a `name` field (plus source /
    # ability-increase metadata), not a bare string. The save granted by that feat must still be
    # credited -- handing the resolver the raw object never resolves and silently drops the grant.
    s = _sheet(feats=[{"name": "Feat Save", "source": "Background X"}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_object_feat_entry_without_grant_is_still_a_mismatch(access):
    # Same object-entry shape, but the feat grants no save -- a3 proficient is still illegal, so
    # resolving object entries must not blanket-suppress the finding.
    s = _sheet(feats=[{"name": "Feat Gen", "source": "Background X"}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


def test_save_proficiency_without_granting_feat_is_still_a_mismatch(access):
    # same a3-proficient sheet, but WITHOUT feat-save -- still illegal (real errors like g035
    # must still be caught).
    s = _sheet(feats=[], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


def test_subclass_granted_save_proficiency_is_legal(access):
    # sub-save (class-a's subclass) grants proficiency in a3 (x3) via the proficiency grant spine
    # (owner_kind='subclass') -- a sheet proficient in it while holding that subclass is legal,
    # even though a3 isn't a class-a save.
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub Save", "level": 3}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_save_proficiency_without_granting_subclass_is_still_a_mismatch(access):
    # same a3-proficient sheet, but WITHOUT sub-save (e.g. Sub A instead) -- still illegal.
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub A", "level": 3}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


def test_level_gated_subclass_save_is_legal_once_class_level_meets_gained_at_level(access):
    # sub-save-late (a level-gated subclass save grant) grants a3 only from class level 7 onward -- at class
    # level 8, proficient in a3 is legal (grant active + present).
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub Save Late", "level": 8}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": True, "modifier": 3},
    })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_level_gated_subclass_save_not_yet_expected_below_gained_at_level(access):
    # same subclass at class level 5 (below gained_at_level=7): the grant is NOT active yet, so
    # NOT being proficient in a3 must not be flagged -- the character must not be expected to
    # have a save their subclass hasn't granted them yet.
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub Save Late", "level": 5}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": False, "modifier": 1},
    })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_level_gated_subclass_save_still_flagged_when_missing_after_gained_at_level(access):
    # same subclass at class level 8 (grant IS active): NOT being proficient in a3 is a real,
    # legitimate error and must still be flagged (mirrors gold error g030).
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub Save Late", "level": 8}], saving_throws={
        "x1": {"proficient": True, "modifier": 4},
        "x2": {"proficient": True, "modifier": 4},
        "x3": {"proficient": False, "modifier": 1},
    })
    assert "save-proficiency-mismatch" in _codes(s, access)


# ── class-level feature save grant (owner_kind='class', gated, non-first entry) ──


def test_class_feature_save_grant_on_non_first_class_entry_is_legal(access):
    # class-b's OWN L7 feature grants an a3 (x3) save. On a multiclass build where class-b is the
    # SECOND entry at level 8 (>= the gate), being proficient in a3 is legal -- proving the check
    # consumes a class's own save grant for a non-first class entry, gated by that entry's level.
    s = _sheet(
        classes=[{"class": "Class A", "level": 3},
                 {"class": "Class B", "subclass": "Sub B", "level": 8}],
        saving_throws={
            "x1": {"proficient": True, "modifier": 4},   # class-a's first-class save a1
            "x2": {"proficient": True, "modifier": 4},   # class-a's first-class save a2
            "x3": {"proficient": True, "modifier": 3},   # class-b's L7 feature save a3
        })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_class_feature_save_grant_below_gate_not_expected(access):
    # class-b as the second entry at level 5 (below the level-7 gate): the grant is NOT active, so
    # NOT being proficient in a3 must not be flagged.
    s = _sheet(
        classes=[{"class": "Class A", "level": 3},
                 {"class": "Class B", "subclass": "Sub B", "level": 5}],
        saving_throws={
            "x1": {"proficient": True, "modifier": 4},
            "x2": {"proficient": True, "modifier": 4},
            "x3": {"proficient": False, "modifier": 1},
        })
    assert "save-proficiency-mismatch" not in _codes(s, access)


def test_class_feature_save_grant_at_gate_missing_flagged(access):
    # class-b at level 8 (grant active) but NOT proficient in a3 -- a real error, still flagged.
    s = _sheet(
        classes=[{"class": "Class A", "level": 3},
                 {"class": "Class B", "subclass": "Sub B", "level": 8}],
        saving_throws={
            "x1": {"proficient": True, "modifier": 4},
            "x2": {"proficient": True, "modifier": 4},
            "x3": {"proficient": False, "modifier": 1},
        })
    assert "save-proficiency-mismatch" in _codes(s, access)
