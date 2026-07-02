"""class_level layer + the resilient orchestrator: all findings at once, and a crashing check never
stops the run. Uses a synthetic, content-neutral ruleset."""
from validator.checks import class_level
from validator.rules import Rules
from validator.validate import validate

# class 'alpha': subclass unlocks at level 3, PB steps at 5
RULES = Rules(class_progression={"alpha": {
    "1": {"proficiency_bonus": 2, "features": ["Spellcasting"]},
    "3": {"proficiency_bonus": 2, "features": ["Alpha Subclass"]},
    "5": {"proficiency_bonus": 3, "features": []},
}}, class_proficiencies={"alpha": {"primary": ["str"]}, "beta": {"primary": ["wis"]}})


def _sheet(level, subclass, pb):
    return {"proficiency_bonus": pb,
            "identity": {"total_level": level,
                         "classes": [{"class": "Alpha", "level": level, "subclass": subclass}]}}


def test_legal_sheet_has_no_violations():
    r = validate(_sheet(5, "Sub", 3), RULES)
    assert r["legal"] and r["complete"] and r["violations"] == []


def test_subclass_too_early():
    r = validate(_sheet(2, "Sub", 2), RULES)
    assert not r["legal"] and "subclass_too_early" in [v["code"] for v in r["violations"]]


def test_subclass_missing():
    r = validate(_sheet(5, None, 3), RULES)
    assert "subclass_missing" in [v["code"] for v in r["violations"]]


def test_bad_proficiency_bonus():
    r = validate(_sheet(5, "Sub", 2), RULES)
    assert "proficiency_bonus" in [v["code"] for v in r["violations"]]


def test_all_errors_reported_at_once():
    r = validate(_sheet(5, None, 2), RULES)   # wrong PB *and* missing subclass on the same sheet
    codes = {v["code"] for v in r["violations"]}
    assert {"proficiency_bonus", "subclass_missing"} <= codes


def test_a_crashing_check_does_not_stop_the_run():
    def boom(sheet, rules):
        raise RuntimeError("kaboom")
    r = validate(_sheet(2, "Sub", 2), RULES, checks=[boom, class_level.check])
    codes = {v["code"] for v in r["violations"]}
    assert "check_crashed" in codes          # the crash was captured…
    assert "subclass_too_early" in codes     # …and the real check still ran
    assert r["complete"] is False            # and the report flags that validation was partial


def _mc_sheet(scores, a_level=3, b_level=3):
    """Multiclass Alpha/Beta with given ability final scores; Alpha has its subclass, Beta needs none."""
    return {"proficiency_bonus": 2,
            "identity": {"total_level": a_level + b_level,
                         "classes": [{"class": "Alpha", "level": a_level, "subclass": "Sub"},
                                     {"class": "Beta", "level": b_level, "subclass": None}]},
            "abilities": {a: {"final": s} for a, s in scores.items()}}


def test_total_level_mismatch():                                 # G1
    s = _mc_sheet({"str": 15, "wis": 15})
    s["identity"]["total_level"] = 99                            # != 3 + 3
    assert "total_level_mismatch" in {v.code for v in class_level.check(s, RULES)}


def test_multiclass_prerequisite_flagged():                      # G2
    s = _mc_sheet({"str": 15, "wis": 10})                        # Beta needs Wis 13+, has 10
    assert "multiclass_prerequisite" in {v.code for v in class_level.check(s, RULES)}


def test_multiclass_prerequisite_ok():                           # G2
    s = _mc_sheet({"str": 15, "wis": 13})
    assert "multiclass_prerequisite" not in {v.code for v in class_level.check(s, RULES)}
