from validator.checks.identity import check


def _sheet(**identity):
    base = {"species": "Species A", "size": "Size A", "creature_type": "Type A",
            "background": "Background A", "total_level": 3, "xp": 900,
            "classes": [{"class": "Class A", "subclass": "Sub A", "level": 3}]}
    base.update(identity)
    return {"identity": base}


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_unknown_class(access):
    assert "unknown-class" in _codes(_sheet(classes=[{"class": "Nope", "level": 3}]), access)


def test_subclass_belongs_to_other_class(access):
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub B", "level": 3}])
    assert "subclass-class-mismatch" in _codes(s, access)


def test_subclass_chosen_too_early(access):
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub A", "level": 2}],
               total_level=2, xp=300)
    assert "subclass-too-early" in _codes(s, access)


def test_subclass_missing_after_unlock(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}])
    codes = _codes(s, access)
    assert "subclass-missing" in codes


def test_total_level_mismatch(access):
    assert "total-level-mismatch" in _codes(_sheet(total_level=5), access)


def test_creature_type_mismatch(access):
    # "Type B" resolves but is not Species A's type ("Type A")
    assert "creature-type-mismatch" in _codes(_sheet(creature_type="Type B"), access)


def test_xp_too_low(access):
    assert "xp-too-low" in _codes(_sheet(xp=0), access)


def test_missing_finding_is_incomplete_not_illegal(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}])
    v = [x for x in check(s, access) if x.code == "subclass-missing"][0]
    assert v.kind == "incomplete"


def test_xp_too_high(access):
    assert "xp-too-high" in _codes(_sheet(xp=2700), access)


def test_malformed_classes_not_a_list(access):
    s = _sheet(classes="oops")
    codes = _codes(s, access)
    assert "malformed-classes" in codes


def test_malformed_level_not_an_int(access):
    s = _sheet(classes=[{"class": "Class A", "subclass": "Sub A", "level": "3"}])
    codes = _codes(s, access)
    assert "malformed-level" in codes
