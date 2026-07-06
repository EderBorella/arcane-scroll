import pytest

from validator.checks.senses import check, _resolve_senses


def _sheet(species="Species A", classes=None, feats=None, senses=None):
    classes = classes if classes is not None else [{"class": "Class A", "level": 3, "subclass": "Sub A"}]
    return {
        "identity": {"species": species, "classes": classes},
        "feats": feats or [],
        "senses": senses or {},
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ---- resolver unit tests ----

def test_resolver_max_not_sum():
    grants = [
        {"sense_id": "darkvision", "range_ft": 60, "extends_existing": 0},
        {"sense_id": "darkvision", "range_ft": 120, "extends_existing": 0},
    ]
    assert _resolve_senses(grants) == {"darkvision": 120}


def test_resolver_extension_adds_on_top():
    grants = [
        {"sense_id": "darkvision", "range_ft": 60, "extends_existing": 0},
        {"sense_id": "darkvision", "range_ft": 30, "extends_existing": 1},
    ]
    assert _resolve_senses(grants) == {"darkvision": 90}


def test_resolver_max_then_extend():
    grants = [
        {"sense_id": "darkvision", "range_ft": 60, "extends_existing": 0},
        {"sense_id": "darkvision", "range_ft": 120, "extends_existing": 0},
        {"sense_id": "darkvision", "range_ft": 30, "extends_existing": 1},
    ]
    assert _resolve_senses(grants) == {"darkvision": 150}


def test_resolver_extension_without_base_is_ignored():
    grants = [
        {"sense_id": "darkvision", "range_ft": 30, "extends_existing": 1},
    ]
    assert _resolve_senses(grants) == {}


def test_resolver_multiple_senses():
    grants = [
        {"sense_id": "darkvision", "range_ft": 60, "extends_existing": 0},
        {"sense_id": "blindsight", "range_ft": 10, "extends_existing": 0},
    ]
    assert _resolve_senses(grants) == {"darkvision": 60, "blindsight": 10}


# ---- check integration tests ----

def test_clean_sheet_species_only(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               senses={"darkvision": 60})
    assert check(s, access) == []


def test_max_not_sum_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               senses={"darkvision": 120})
    assert check(s, access) == []


def test_max_not_sum_violation(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               senses={"darkvision": 180})
    assert "sense-range-mismatch" in _codes(s, access)


def test_extending_feat_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               feats=[{"name": "Feat Gen", "source": "asi"}],
               senses={"darkvision": 90})
    assert check(s, access) == []


def test_max_plus_extend_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               feats=[{"name": "Feat Gen", "source": "asi"}],
               senses={"darkvision": 150})
    assert check(s, access) == []


def test_missing_sense(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               senses={})
    assert "sense-missing" in _codes(s, access)


def test_ungranted_sense_is_illegal(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               senses={"darkvision": 60, "blindsight": 30})
    assert "sense-ungranted" in _codes(s, access)


def test_blindsight_grant_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               feats=[{"name": "Feat Rep", "source": "asi"}],
               senses={"darkvision": 60, "blindsight": 10})
    assert check(s, access) == []


def test_subclass_grant_level_gated(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2, "subclass": "Sub A"}],
               senses={"darkvision": 120})
    assert "sense-range-mismatch" in _codes(s, access)


def test_no_sense_grants_returns_empty(access):
    s = _sheet(species="Species Unknown", classes=[{"class": "Class B", "level": 1}],
               senses={"darkvision": 60})
    assert _codes(s, access) == {"sense-ungranted"}


def test_subclass_level_3_grants_appears_at_level_3(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               senses={"darkvision": 120})
    assert check(s, access) == []
