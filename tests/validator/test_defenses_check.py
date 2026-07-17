import pytest

from validator.checks.defenses import check


def _sheet(species="Species A", classes=None, feats=None, defenses=None):
    classes = classes if classes is not None else [{"class": "Class A", "level": 3, "subclass": "Sub A"}]
    return {
        "identity": {"species": species, "classes": classes},
        "feats": feats or [],
        "defenses": defenses or {},
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ---- resistance tests ----

def test_clean_resistances(access):
    s = _sheet(
        classes=[{"class": "Class A", "level": 3}],
        defenses={"resistances": ["poison"]})
    assert check(s, access) == []


def test_missing_resistance(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               defenses={"resistances": []})
    assert "resistance-missing" in _codes(s, access)


def test_ungranted_resistance(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               defenses={"resistances": ["cold"]})
    assert "resistance-ungranted" in _codes(s, access)
    assert "resistance-missing" in _codes(s, access)


def test_multiple_owners_resistances(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               feats=[{"name": "Feat Gen", "source": "asi"}],
               defenses={"resistances": ["poison", "fire"]})
    assert check(s, access) == []


def test_multiple_owners_missing_one(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3}],
               feats=[{"name": "Feat Gen", "source": "asi"}],
               defenses={"resistances": ["poison"]})
    assert "resistance-missing" in _codes(s, access)


# ---- condition immunity tests ----

def test_clean_condition_immunity(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               defenses={"resistances": ["poison"], "condition_immunities": ["charmed"]})
    assert check(s, access) == []


def test_condition_immunity_missing(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               defenses={"resistances": ["poison"], "condition_immunities": []})
    assert "condition-immunity-missing" in _codes(s, access)


def test_condition_immunity_ungranted(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               defenses={"resistances": ["poison"],
                         "condition_immunities": ["frightened"]})
    assert "condition-immunity-ungranted" in _codes(s, access)


def test_subclass_immunity_at_correct_level(access):
    s = _sheet(classes=[{"class": "Class A", "level": 3, "subclass": "Sub A"}],
               defenses={"resistances": ["poison"], "condition_immunities": ["charmed"]})
    assert check(s, access) == []


def test_subclass_immunity_below_level(access):
    s = _sheet(classes=[{"class": "Class A", "level": 2, "subclass": "Sub A"}],
               defenses={"resistances": ["poison"], "condition_immunities": ["charmed"]})
    assert "condition-immunity-ungranted" in _codes(s, access)


# ---- multi-axis species variants (T100) ----

def _variant_sheet(variants, resistances):
    """A Species MV build (two variant axes) with per-axis picks and declared resistances."""
    return {
        "identity": {"species": "Species MV", "species_variants": variants,
                     "classes": [{"class": "Class A", "level": 3}]},
        "feats": [],
        "defenses": {"resistances": resistances},
    }


def test_multi_axis_each_axis_resolved(access):
    # axis-a Variant A -> fire, axis-b Variant C -> poison; both expected, both declared -> clean.
    s = _variant_sheet({"axis-a": "Variant A", "axis-b": "Variant C"}, ["fire", "poison"])
    assert check(s, access) == []


def test_multi_axis_missing_one_axis_resistance(access):
    # declaring only one axis's resistance leaves the other axis's expected resistance missing.
    s = _variant_sheet({"axis-a": "Variant A", "axis-b": "Variant C"}, ["fire"])
    assert "resistance-missing" in _codes(s, access)


def test_multi_axis_pick_resolves_per_axis(access):
    # axis-b Variant D -> cold (not poison); a sheet declaring poison is ungranted.
    s = _variant_sheet({"axis-a": "Variant A", "axis-b": "Variant D"}, ["cold", "fire", "poison"])
    assert "resistance-ungranted" in _codes(s, access)


def test_single_axis_field_still_resolves(access):
    # backward compatibility: the single-axis species_variant field resolves the one axis it matches.
    s = {
        "identity": {"species": "Species V", "species_variant": "Variant A",
                     "classes": [{"class": "Class A", "level": 3}]},
        "feats": [],
        "defenses": {"resistances": ["fire"]},
    }
    assert check(s, access) == []
