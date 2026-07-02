"""proficiencies layer: saves + armour/weapon/tool proficiencies from the first class; class skills
count + on-list; background skills all present; expertise sits on a proficient skill and stays within
what the classes grant. Synthetic, content-neutral rules."""
from validator.checks import proficiencies
from validator.rules import Rules

R = Rules(class_proficiencies={"alpha": {"saving_throws": ["str", "con"],
                                         "skills": {"choose": 2, "from": ["Athletics", "Stealth", "Arcana"]},
                                         "armor": ["light", "medium"], "weapons": ["simple", "martial"],
                                         "tools": {"fixed": ["Kit-A"]}}},
          class_progression={"alpha": {"1": {"features": ["Expertise"]},
                                       "3": {"features": ["Expertise"]}}},
          backgrounds={"scholar": {"skills": ["Insight", "Religion"]}})


def _sheet(saves_prof, skills, background=None, level=5,
           armor=("Light Armor", "Medium Armor"), weapons=("Simple Weapons", "Martial Weapons"),
           tools=("Kit-A",), expertise=()):
    return {"identity": {"classes": [{"class": "Alpha", "level": level}], "background": background},
            "saving_throws": {ab: {"proficient": ab in saves_prof, "modifier": 0}
                              for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "skills": {name: {"proficient": True, "source": src, "expertise": name in expertise}
                       for name, src in skills},
            "proficiencies": {"armor": list(armor), "weapons": list(weapons), "tools": list(tools)}}


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


def test_armor_proficiency_missing():
    assert "armor_proficiency_missing" in _codes(
        _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], armor=("Light Armor",)))


def test_weapon_proficiency_missing():
    assert "weapon_proficiency_missing" in _codes(
        _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], weapons=("Simple Weapons",)))


def test_all_armor_token_expands():
    # 'All armor' covers light+medium+heavy, so nothing is missing.
    assert "armor_proficiency_missing" not in _codes(
        _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], armor=("All Armor",)))


def test_tool_proficiency_missing():
    assert "tool_proficiency_missing" in _codes(
        _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], tools=()))


def test_expertise_requires_proficiency():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")])
    s["skills"]["Arcana"] = {"proficient": False, "source": None, "expertise": True}
    assert "expertise_without_proficiency" in _codes(s)


def test_expertise_within_grant_ok():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")],
               expertise=("Athletics", "Stealth"))          # 2 ≤ 4 granted by level 5
    assert "expertise_over_grant" not in _codes(s)


def test_expertise_over_grant_warns():
    skills = [("Athletics", "class"), ("Stealth", "class"), ("Arcana", "class"),
              ("Insight", "background"), ("Religion", "background")]
    s = _sheet(["str", "con"], skills, expertise=tuple(n for n, _ in skills))   # 5 > 4 granted
    assert "expertise_over_grant" in _codes(s)
