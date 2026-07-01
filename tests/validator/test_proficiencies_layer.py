"""proficiencies layer (2024): saves from the first class; class skills count + on-list. Synthetic rules."""
from validator.checks import proficiencies
from validator.rules import Rules

R = Rules(class_proficiencies={"alpha": {"saving_throws": ["str", "con"],
                                         "skills": {"choose": 2, "from": ["Athletics", "Stealth", "Arcana"]}}})


def _sheet(saves_prof, skills):
    return {"identity": {"classes": [{"class": "Alpha", "level": 5}]},
            "saving_throws": {ab: {"proficient": ab in saves_prof, "modifier": 0}
                              for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "skills": {name: {"proficient": True, "source": src} for name, src in skills}}


def _codes(s):
    return {v.code for v in proficiencies.check(s, R)}


def test_legal():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class"), ("Insight", "background")])
    assert proficiencies.check(s, R) == []


def test_wrong_saves():
    assert "saving_throws" in _codes(_sheet(["str", "dex"], [("Athletics", "class"), ("Stealth", "class")]))


def test_skill_count():
    assert "skill_count" in _codes(_sheet(["str", "con"], [("Athletics", "class")]))   # only 1, needs 2


def test_skill_off_list():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Deception", "class")])       # Deception not on list
    assert "skill_off_list" in _codes(s)
