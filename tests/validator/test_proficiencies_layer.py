"""proficiencies layer (2024): saves from the first class; class skills count + on-list; background
skills all present. Synthetic, content-neutral rules."""
from validator.checks import proficiencies
from validator.rules import Rules

R = Rules(class_proficiencies={"alpha": {"saving_throws": ["str", "con"],
                                         "skills": {"choose": 2, "from": ["Athletics", "Stealth", "Arcana"]}}},
          backgrounds={"scholar": {"skills": ["Insight", "Religion"]}})


def _sheet(saves_prof, skills, background=None):
    return {"identity": {"classes": [{"class": "Alpha", "level": 5}], "background": background},
            "saving_throws": {ab: {"proficient": ab in saves_prof, "modifier": 0}
                              for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "skills": {name: {"proficient": True, "source": src} for name, src in skills}}


def _codes(s):
    return {v.code for v in proficiencies.check(s, R)}


def test_legal():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class"),
                                ("Insight", "background"), ("Religion", "background")], background="Scholar")
    assert proficiencies.check(s, R) == []


def test_wrong_saves():
    assert "saving_throws" in _codes(_sheet(["str", "dex"], [("Athletics", "class"), ("Stealth", "class")]))


def test_skill_count():
    assert "skill_count" in _codes(_sheet(["str", "con"], [("Athletics", "class")]))     # only 1, needs 2


def test_skill_off_list():
    assert "skill_off_list" in _codes(_sheet(["str", "con"], [("Athletics", "class"), ("Deception", "class")]))


def test_background_skills_missing():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class"), ("Insight", "background")],
               background="Scholar")   # Scholar grants Insight + Religion; Religion missing
    assert "background_skills_missing" in _codes(s)


def test_background_skills_present():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class"),
                                ("Insight", "background"), ("Religion", "background")], background="Scholar")
    assert "background_skills_missing" not in _codes(s)
