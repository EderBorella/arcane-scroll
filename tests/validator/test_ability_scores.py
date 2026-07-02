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


def test_background_increase_cannot_exceed_20():
    over = {"int": {"base": 20, "racial_bonus": 2, "final": 22, "modifier": 6}}
    assert "background_increase_above_20" in _codes(_sheet("Scholar", {"wis": 1}, overrides=over))


def test_epic_boon_final_up_to_30_ok():
    # base 18 + background +2 = 20 (legal), then Epic Boons push final to 30 (legal, ≤ 30).
    over = {"int": {"base": 18, "background_bonus": 2, "final": 30, "modifier": 10}}
    codes = _codes(_sheet("Scholar", {"wis": 1}, overrides=over))
    assert "ability_above_30" not in codes and "background_increase_above_20" not in codes


def test_final_above_30_flagged():
    over = {"int": {"base": 18, "background_bonus": 2, "final": 31, "modifier": 10}}
    assert "ability_above_30" in _codes(_sheet("Scholar", {"wis": 1}, overrides=over))


def test_background_bonus_field_is_used():
    # The granted increase is read from background_bonus (not the legacy racial_bonus).
    inc = {"int": 2, "wis": 1}
    ab = {a: {"base": 10, "background_bonus": inc.get(a, 0), "final": 10 + inc.get(a, 0), "modifier": 0}
          for a in ("str", "dex", "con", "int", "wis", "cha")}
    assert ability_scores.check({"abilities": ab, "identity": {"background": "Scholar"}}, R) == []
