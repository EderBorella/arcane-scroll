"""feats layer: feats taken ≤ available slots (Origin + ASI/Epic-Boon features); level & ability
prerequisites met; non-repeatable feats not taken twice. Synthetic, content-neutral rules."""
from validator.checks import feats
from validator.rules import Rules

R = Rules(
    class_progression={"alpha": {"1": {"features": ["Spellcasting"]},
                                 "4": {"features": ["Ability Score Improvement"]},
                                 "8": {"features": ["Ability Score Improvement"]},
                                 "19": {"features": ["Epic Boon"]}}},
    feats={"feat-a": {"category": "Origin", "repeatable": False},
           "feat-b": {"category": "General", "repeatable": False,
                      "prereq": {"level": 4, "abilities": [["str", "dex"]]}},
           "feat-c": {"category": "General", "repeatable": False, "prereq": {"class": "alpha", "level": 5}},
           "feat-rep": {"category": "General", "repeatable": True}})


def _sheet(feat_list, level=8, background="bg-a", classes=None, abilities=None):
    classes = classes or [{"class": "Alpha", "level": level}]
    return {"identity": {"total_level": level, "background": background, "classes": classes},
            "abilities": abilities or {ab: {"final": 15} for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "feats": feat_list}


def _codes(s):
    return {v.code for v in feats.check(s, R)}


def _f(name):
    return {"name": name, "source": "Background"}


def test_within_slots_and_prereqs_legal():          # Alpha 8 + background → 3 slots (Origin + ASI@4,8)
    assert feats.check(_sheet([_f("feat-a"), _f("feat-b")]), R) == []


def test_no_feats_field_is_skipped():
    assert feats.check({"identity": {"classes": []}}, R) == []


def test_feat_slot_overrun():
    s = _sheet([_f("feat-a"), _f("feat-b"), _f("feat-rep"), _f("feat-rep")])  # 4 > 3 slots
    assert "feat_slot_overrun" in _codes(s)


def test_no_background_drops_origin_slot():
    s = _sheet([_f("feat-a"), _f("feat-b"), _f("feat-rep")], background=None)  # 3 > 2 (ASI@4,8 only)
    assert "feat_slot_overrun" in _codes(s)


def test_prereq_character_level():
    s = _sheet([_f("feat-b")], level=3)               # feat-b needs level 4+
    assert "feat_prereq_level" in _codes(s)


def test_prereq_class_level():
    s = _sheet([_f("feat-c")], classes=[{"class": "Alpha", "level": 3}], level=3)  # feat-c needs alpha 5+
    assert "feat_prereq_level" in _codes(s)


def test_prereq_ability_unmet():
    s = _sheet([_f("feat-b")], abilities={ab: {"final": 10} for ab in ("str", "dex", "con", "int", "wis", "cha")})
    assert "feat_prereq_ability" in _codes(s)


def test_prereq_ability_any_of_satisfied():
    # feat-b needs str OR dex ≥ 13; dex 15 satisfies even though str 10
    ab = {"str": {"final": 10}, "dex": {"final": 15}, "con": {"final": 10},
          "int": {"final": 10}, "wis": {"final": 10}, "cha": {"final": 10}}
    assert "feat_prereq_ability" not in _codes(_sheet([_f("feat-b")], abilities=ab))


def test_non_repeatable_taken_twice():
    assert "feat_repeated" in _codes(_sheet([_f("feat-a"), _f("feat-a")]))


def test_repeatable_taken_twice_ok():
    assert "feat_repeated" not in _codes(_sheet([_f("feat-rep"), _f("feat-rep")]))


def test_unknown_feat_warns():
    assert "unknown_feat" in _codes(_sheet([_f("feat-x")]))
