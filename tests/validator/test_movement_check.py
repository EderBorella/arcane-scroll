import pytest

from validator.checks.movement import check, _resolve_speeds


def _sheet(species="Species A", classes=None, feats=None, speed=None):
    classes = classes if classes is not None else [{"class": "Class B", "level": 3}]
    return {
        "identity": {"species": species, "classes": classes},
        "feats": feats or [],
        "combat": {"speed": speed} if speed is not None else {},
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ---- integration: clean sheets ----

def test_species_only_walk_clean(access):
    s = _sheet(speed={"walk": 30})
    assert check(s, access) == []


def test_additive_feat_walk_clean(access):
    s = _sheet(feats=[{"name": "Feat Gen", "source": "asi"}],
               speed={"walk": 40})
    assert check(s, access) == []


def test_sets_total_overrides(access):
    s = _sheet(feats=[{"name": "Feat Over", "source": "asi"}],
               speed={"walk": 30, "climb": 20})
    assert check(s, access) == []


def test_equals_walk_swim_clean(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               speed={"walk": 40, "swim": 40})
    assert check(s, access) == []


def test_multiple_modes_walk_plus_swim(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               feats=[{"name": "Feat Gen", "source": "asi"}],
               speed={"walk": 50, "swim": 50})
    assert check(s, access) == []


def test_equals_walk_fly_clean(access):
    s = _sheet(feats=[{"name": "Feat Rep", "source": "asi"}],
               speed={"walk": 30, "fly": 30})
    assert check(s, access) == []


# ---- integration: violations ----

def test_missing_mode_on_sheet(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               speed={})
    assert "movement-missing" in _codes(s, access)


def test_wrong_speed_value(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               speed={"walk": 35})
    assert "movement-speed-mismatch" in _codes(s, access)


def test_ungranted_mode_on_sheet(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               speed={"walk": 30, "fly": 60})
    assert "movement-ungranted" in _codes(s, access)


def test_level_gated_subclass_grant_at_correct_level(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               speed={"walk": 40, "swim": 40})
    assert check(s, access) == []


def test_level_gated_subclass_grant_below_level(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2, "subclass": "Sub A"}],
               speed={"walk": 30, "swim": 30})
    assert "movement-ungranted" in _codes(s, access)


def test_class_resource_speed_bonus_level2(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2}],
               speed={"walk": 40})
    assert check(s, access) == []


def test_class_resource_speed_bonus_level6(access):
    s = _sheet(classes=[{"class": "Class A", "level": 6}],
               speed={"walk": 45})
    assert check(s, access) == []


# ---- resolver unit tests ----

def test_resolver_baseline_walk():
    assert _resolve_speeds([], 30, []) == {"walk": 30}


def test_resolver_additive_sums():
    grants = [
        {"movement_mode_id": "walk", "feet": 10, "equals_walk": 0, "sets_total": 0, "additive": 1},
        {"movement_mode_id": "walk", "feet": 5, "equals_walk": 0, "sets_total": 0, "additive": 1},
    ]
    assert _resolve_speeds(grants, 30, []) == {"walk": 45}


def test_resolver_sets_total_max():
    grants = [
        {"movement_mode_id": "fly", "feet": 30, "equals_walk": 0, "sets_total": 1, "additive": 0},
        {"movement_mode_id": "fly", "feet": 60, "equals_walk": 0, "sets_total": 1, "additive": 0},
    ]
    assert _resolve_speeds(grants, 30, []) == {"walk": 30, "fly": 60}


def test_resolver_equals_walk_follows_resolved_walk():
    grants = [
        {"movement_mode_id": "walk", "feet": 10, "equals_walk": 0, "sets_total": 0, "additive": 1},
        {"movement_mode_id": "swim", "feet": None, "equals_walk": 1, "sets_total": 0, "additive": 0},
    ]
    assert _resolve_speeds(grants, 30, []) == {"walk": 40, "swim": 40}


def test_resolver_class_bonus_adds_to_walk():
    assert _resolve_speeds([], 30, [10]) == {"walk": 40}


def test_resolver_multiple_class_bonuses_take_max():
    assert _resolve_speeds([], 30, [10, 15]) == {"walk": 45}
