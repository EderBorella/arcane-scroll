"""masteries layer: each mastered weapon has a mastery property; a single-class character's count
matches the class's Weapon Mastery count at its level; untracked classes skip the count. Synthetic,
content-neutral rules."""
from validator.checks import masteries
from validator.rules import Rules

R = Rules(weapon_masteries={"weapon-a": "prop-a", "weapon-b": "prop-b", "weapon-c": "prop-c"},
          weapon_mastery_counts={"class-a": {"1": 2, "5": 3}, "class-b": {"1": 2}})


def _sheet(classes, mastered):
    return {"identity": {"classes": [{"class": c, "level": l} for c, l in classes]},
            "weapon_masteries": mastered}


def _codes(s):
    return {v.code for v in masteries.check(s, R)}


def test_legal_count_and_eligibility():         # class-a L5 grants 3
    assert masteries.check(_sheet([("class-a", 5)], ["weapon-a", "weapon-b", "weapon-c"]), R) == []


def test_weapon_without_mastery():              # 'weapon-x' is not a masterable weapon
    assert "weapon_has_no_mastery" in _codes(_sheet([("class-a", 5)], ["weapon-a", "weapon-x", "weapon-b"]))


def test_count_too_few_is_error():              # class-a L5 grants 3; only 2 mastered — illegal
    viols = [v for v in masteries.check(_sheet([("class-a", 5)], ["weapon-a", "weapon-b"]), R)
             if v.code == "mastery_count"]
    assert viols and all(v.severity == "error" for v in viols)


def test_count_too_many_is_advisory():          # class-a L1 grants 2; 3 mastered — extras may be a feat/subclass
    viols = [v for v in masteries.check(_sheet([("class-a", 1)], ["weapon-a", "weapon-b", "weapon-c"]), R)
             if v.code == "mastery_count"]
    assert viols and all(v.severity == "warning" for v in viols)


def test_count_between_breakpoints():           # class-a {1:2, 5:3} → level 3 uses the level-1 row (2)
    assert R.weapon_mastery_count("class-a", 3) == 2
    assert R.weapon_mastery_count("class-a", 5) == 3
    assert R.weapon_mastery_count("class-z", 5) is None


def test_untracked_class_skips_count():         # class-z grants no mastery in the data → no count error
    assert "mastery_count" not in _codes(_sheet([("class-z", 5)], ["weapon-a"]))
