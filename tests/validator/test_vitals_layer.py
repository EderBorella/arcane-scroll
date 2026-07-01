"""vitals layer (2024): HP within [min, max] for hit dice + Con; hit-dice pool matches; initiative =
Dex mod; passive Perception = 10 + Perception. Synthetic, content-neutral rules."""
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


def test_initiative_mismatch():
    assert "initiative" in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, init=5, dexmod=2))


def test_passive_perception_mismatch():
    assert "passive_perception" in _codes(_sheet([("alpha", 5)], hp=44, hit_dice={"d10": 5}, pp=99, perc=3))
