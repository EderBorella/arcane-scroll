from validator.checks.feats import check


def _level4():
    return [{"class": "Class A", "level": 4}]


def _a1(final):
    return {"a1": {"final": final}}


def _sheet(feats=None, classes=None, background="Background A", species=None, abilities=None):
    ident = {"background": background}
    if classes is not None:
        ident["classes"] = classes
    if species is not None:
        ident["species"] = species
    sheet = {"identity": ident, "feats": feats if feats is not None else []}
    if abilities is not None:
        sheet["abilities"] = abilities
    return sheet


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    sheet = _sheet(feats=["Feat Origin", "Feat Gen"], classes=_level4())
    assert check(sheet, access) == []


def test_unknown_feat_name(access):
    sheet = _sheet(feats=["Nonexistent Feat"], classes=_level4())
    assert "unknown-feat" in _codes(sheet, access)


def test_repeatable_feat_taken_twice_is_fine(access):
    # class-a level 8 has two ASI slots (cf-asi4 + cf-asi8), enough for two picks of a
    # repeatable feat
    sheet = _sheet(feats=["Feat Rep", "Feat Rep"], classes=[{"class": "Class A", "level": 8}])
    assert check(sheet, access) == []


def test_non_repeatable_feat_taken_twice_is_illegal(access):
    sheet = _sheet(feats=["Feat Gen", "Feat Gen"], classes=_level4())
    assert "feat-repeated" in _codes(sheet, access)


def test_too_many_feats_over_asi_slots(access):
    # class-a level 4 has 1 ASI slot; two distinct general feats exceeds it
    sheet = _sheet(feats=["Feat Gen", "Feat Rep"], classes=_level4())
    assert "too-many-feats" in _codes(sheet, access)


def test_too_many_origin_feats(access):
    # bg-a grants exactly 1 origin feat slot
    sheet = _sheet(feats=["Feat Origin", "Feat Origin"], classes=_level4())
    assert "too-many-origin-feats" in _codes(sheet, access)


def test_origin_feat_budget_comes_from_background_feat_id(access):
    # bg-a's origin budget is sourced from background.feat_id (='feat-origin'), not grant_feat --
    # one origin feat with that background is fully legal.
    sheet = _sheet(feats=["Feat Origin"], classes=_level4())
    assert check(sheet, access) == []


def test_background_without_feat_id_grants_no_origin_budget(access):
    # bg-b has no feat_id (no origin grant) and species is unset -- a origin feat is still
    # illegal without a granting source, even though it's the only feat taken.
    sheet = _sheet(feats=["Feat Origin"], classes=_level4(), background="Background B")
    assert "too-many-origin-feats" in _codes(sheet, access)


def test_prereq_unmet_on_level(access):
    sheet = _sheet(feats=["Feat Pre"], classes=[{"class": "Class A", "level": 3}], abilities=_a1(15))
    assert "feat-prereq-unmet" in _codes(sheet, access)


def test_prereq_unmet_on_ability(access):
    sheet = _sheet(feats=["Feat Pre"], classes=_level4(), abilities=_a1(10))
    assert "feat-prereq-unmet" in _codes(sheet, access)


def test_prereq_met_is_eligible(access):
    sheet = _sheet(feats=["Feat Pre"], classes=_level4(), abilities=_a1(15))
    assert check(sheet, access) == []


def test_malformed_feats_not_a_list_does_not_raise(access):
    sheet = _sheet(classes=_level4())
    sheet["feats"] = "x"
    assert "malformed-feats" in _codes(sheet, access)


def test_malformed_identity_not_a_dict_does_not_raise(access):
    sheet = _sheet(classes=_level4())
    sheet["identity"] = "oops"
    assert isinstance(check(sheet, access), list)
