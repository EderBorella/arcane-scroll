"""ability_scores layer: background-granted ASIs must land on the background's abilities in a
legal pattern; final scores cap at 20. Synthetic, content-neutral rules."""
from validator.checks import ability_scores
from validator.rules import Rules

R = Rules(backgrounds={"scholar": {"abilities": ["int", "wis", "cha"]}})


def _sheet(background, bumps, overrides=None):
    ab = {}
    for a in ("str", "dex", "con", "int", "wis", "cha"):
        rb = bumps.get(a, 0)
        ab[a] = {"base": 10, "racial_bonus": rb, "final": 10 + rb, "modifier": (rb) // 2}
    if overrides:
        ab.update(overrides)
    return {"abilities": ab, "identity": {"background": background}}


def _codes(sheet):
    return {v.code for v in ability_scores.check(sheet, R)}


def test_legal_plus2_plus1():
    assert ability_scores.check(_sheet("Scholar", {"int": 2, "wis": 1}), R) == []


def test_legal_plus1_times_three():
    assert ability_scores.check(_sheet("Scholar", {"int": 1, "wis": 1, "cha": 1}), R) == []


def test_increase_off_background():
    assert "asi_off_background" in _codes(_sheet("Scholar", {"str": 1, "int": 2}))


def test_species_style_plus1_all():   # the exact species-based generator gap (e.g. +1 to everything)
    codes = _codes(_sheet("Scholar", {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1}))
    assert "asi_off_background" in codes and "asi_pattern" in codes


def test_missing_background_asi():
    assert "asi_missing" in _codes(_sheet("Scholar", {}))


def test_cap_at_20():
    over = {"int": {"base": 20, "racial_bonus": 2, "final": 22, "modifier": 6}}
    assert "ability_above_20" in _codes(_sheet("Scholar", {"wis": 1}, overrides=over))
