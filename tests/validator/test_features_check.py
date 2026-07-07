from validator.checks.features import check, _norm_name


def _sheet(classes=None, species="Species A", features=None):
    classes = classes if classes is not None else [{"class": "Class A", "level": 1}]
    sheet = {"identity": {"species": species, "classes": classes}}
    if features is not None:
        sheet["features"] = features
    return sheet


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def _nf(name):
    return {"name": name}


def test_norm_name_strips_parenthetical():
    assert _norm_name("Feat D (one use)") == "feat d"


def test_norm_name_lowercases():
    assert _norm_name("Feat A") == "feat a"


def test_norm_name_strips_whitespace():
    assert _norm_name("  Feat A  ") == "feat a"


def test_clean_sheet_correct_features(access):
    s = _sheet(features=[_nf("Feat A"), _nf("Feat B")])
    assert check(s, access) == []


def test_missing_class_feature(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2}],
               features=[_nf("Feat A"), _nf("Feat B")])
    assert "feature-missing" in _codes(s, access)


def test_ungranted_feature(access):
    s = _sheet(features=[_nf("Feat A"), _nf("Feat B"), _nf("Fake Feature")])
    assert "feature-ungranted" in _codes(s, access)


def test_subclass_feature_present(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D (one use)"),
                         _nf("Sub Feat A"), _nf("Aspect of the Wilds")])
    assert check(s, access) == []


def test_subclass_feature_below_level_not_expected(access):
    s = _sheet(classes=[{"class": "Class A", "level": 5, "subclass": "Sub A"}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D (one use)"),
                         _nf("Sub Feat A"),
                         _nf("Sub Feat B")])
    assert "feature-ungranted" in _codes(s, access)


def test_subclass_feature_at_correct_level_expected(access):
    s = _sheet(classes=[{"class": "Class A", "level": 6, "subclass": "Sub A"}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D (one use)"),
                         _nf("Sub Feat A"), _nf("Sub Feat B"), _nf("Aspect of the Wilds"),
                         _nf("Ability Score Improvement")])
    assert check(s, access) == []


def test_valid_subclass_detail(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A",
                         "subclass_detail": "Owl"}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D (one use)"),
                         _nf("Sub Feat A"), _nf("Aspect of the Wilds")])
    assert check(s, access) == []


def test_invalid_subclass_detail(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A",
                         "subclass_detail": "Eagle"}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D (one use)"),
                         _nf("Sub Feat A"), _nf("Aspect of the Wilds")])
    assert "feature-detail-option-invalid" in _codes(s, access)


def test_parenthetical_name_matching(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat C"), _nf("Feat D")])
    assert check(s, access) == []


def test_no_features_key_treated_as_empty(access):
    s = _sheet()
    s.pop("features", None)
    assert "feature-missing" in _codes(s, access)


def test_features_not_a_list_is_malformed(access):
    s = _sheet()
    s["features"] = "not a list"
    assert "malformed-features" in _codes(s, access)


def test_class_feature_from_second_class(access):
    s = _sheet(classes=[{"class": "Class B", "level": 1}],
               features=[_nf("Feat X")])
    assert check(s, access) == []


def test_multiple_classes(access):
    s = _sheet(classes=[{"class": "Class A", "level": 1},
                        {"class": "Class B", "level": 1}],
               features=[_nf("Feat A"), _nf("Feat B"), _nf("Feat X")])
    assert check(s, access) == []


def test_below_level_feature_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 1}],
               features=[_nf("Feat A"), _nf("Feat B")])
    assert check(s, access) == []
