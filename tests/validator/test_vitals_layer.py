"""vitals layer: HP within [min, max] for hit dice + Con (per-level minimum-1 floor); hit-dice pool
matches; initiative ≥ Dex mod and passive Perception ≥ 10 + Perception (bonuses are legal, only a
value below the baseline is flagged). Synthetic, content-neutral rules."""
from validator.checks import vitals
from validator.rules import Rules

R = Rules(hit_dice={"alpha": 10, "beta": 6})


def _sheet(classes, hp, hit_dice, con=2, init=2, dexmod=2, pp=None, perc=None):
    total = sum(l for _, l in classes)
    sheet = {"identity": {"total_level": total, "classes": [{"class": c, "level": l} for c, l in classes]},
             "combat": {"hit_dice": hit_dice, "hit_points": {"max": hp}, "initiative": init},
             "abilities": {"con": {"modifier": con}, "dex": {"modifier": dexmod}}}
    if pp is not None:
        sheet["passive_perception"] = pp
        sheet["skills"] = {"Perception": {"modifier": perc}}
    return sheet


def _codes(s):
    return {v.code for v in vitals.check(s, R)}


def test_legal_hp_and_pool():           # alpha d10 L5, Con +2: range [24, 60]; 44 is fine
    assert vitals.check(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}), R) == []


def test_hit_dice_pool_mismatch():      # wrong die size for the class
    assert "hit_dice_pool" in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d8": 5}))


def test_hp_out_of_range():
    assert "hp_out_of_range" in _codes(_sheet([("alpha", 5)], hp=200, hit_dice={"d10": 5}))


def test_multiclass_pool():
    s = _sheet([("alpha", 3), ("beta", 2)], hp=40, hit_dice={"d10": 3, "d6": 2})
    assert "hit_dice_pool" not in _codes(s)


def test_hp_negative_con_floor():
    # alpha d10 L5, Con -3: new min = (10-3) + 4*max(1,-2) = 11; HP 5 is illegally low (old formula
    # wrongly permitted it). max = 50-15 = 35.
    assert "hp_out_of_range" in _codes(_sheet([("alpha", 5)], hp=5, hit_dice={"d10": 5}, con=-3))


def test_initiative_below_dex_flagged():
    assert "initiative" in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, init=1, dexmod=2))


def test_initiative_bonus_is_legal():
    # init = Dex mod + proficiency bonus (Alert feat) — an extra bonus must NOT be flagged.
    assert "initiative" not in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, init=5, dexmod=2))


def test_passive_perception_below_baseline_flagged():
    assert "passive_perception" in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, pp=10, perc=3))


def test_passive_perception_bonus_is_legal():
    # advantage on Perception adds +5 to the passive score — above the baseline is legal.
    assert "passive_perception" not in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, pp=18, perc=3))
