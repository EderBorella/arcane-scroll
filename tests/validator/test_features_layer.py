"""features layer: class features present by level (excluding subclass / ASI / Epic-Boon markers),
and choice-count features carry the right number of picks. Synthetic, content-neutral rules."""
from validator.checks import features
from validator.rules import Rules

R = Rules(
    class_progression={"alpha": {
        "1": {"features": ["Feature-A", "Pick-Feature", "Alpha Subclass", "Feature-B"]},
        "2": {"features": ["Feature-C"]},
        "4": {"features": ["Ability Score Improvement"]}}},
    feature_choice_counts={"alpha": {"Pick-Feature": {"1": 2, "2": 2, "4": 3}}})


def _sheet(feats_with_choices, level=2):
    feats = []
    for name, choices in feats_with_choices:
        f = {"name": name, "source": "x"}
        if choices is not None:
            f["choices"] = choices
        feats.append(f)
    return {"identity": {"classes": [{"class": "alpha", "level": level}]}, "features": feats}


def _codes(s):
    return {v.code for v in features.check(s, R)}


_ALL = [("Feature-A", None), ("Pick-Feature", ["x", "y"]), ("Feature-B", None), ("Feature-C", None)]


def test_all_class_features_present_and_counts_ok():
    assert features.check(_sheet(_ALL), R) == []          # subclass/ASI markers not required


def test_feature_missing():
    partial = [f for f in _ALL if f[0] != "Feature-C"]     # drop a level-≤2 feature
    assert "feature_missing" in _codes(_sheet(partial))


def test_subclass_and_asi_markers_not_required():
    # never include 'Alpha Subclass' or 'Ability Score Improvement'; even at level 4 they're not flagged
    assert "feature_missing" not in {v.code for v in features.check(_sheet(_ALL, level=4), R)
                                     if "subclass" in v.message.lower() or "improvement" in v.message.lower()}


def test_choice_count_wrong():
    wrong = [("Feature-A", None), ("Pick-Feature", ["x"]), ("Feature-B", None), ("Feature-C", None)]  # 1, needs 2
    assert "feature_choice_count" in _codes(_sheet(wrong))


def test_choice_count_scales_with_level():
    # at level 4 the pick-feature grants 3; giving 2 is now wrong
    s = _sheet([("Feature-A", None), ("Pick-Feature", ["x", "y"]), ("Feature-B", None),
                ("Feature-C", None)], level=4)
    assert "feature_choice_count" in _codes(s)


def test_no_classes_is_skipped():
    assert features.check({"identity": {"classes": []}, "features": []}, R) == []
