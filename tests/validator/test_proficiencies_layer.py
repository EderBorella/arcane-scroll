"""proficiencies layer: saves + armour/weapon/tool proficiencies from the first class; class skills
count + on-list; background skills all present; expertise sits on a proficient skill and stays within
what the classes grant. Synthetic, content-neutral rules."""
from validator.checks import proficiencies
from validator.rules import Rules

R = Rules(class_proficiencies={"alpha": {"saving_throws": ["str", "con"],
                                         "skills": {"choose": 2, "from": ["Athletics", "Stealth", "Arcana"]},
                                         "armor": ["light", "medium"], "weapons": ["simple", "martial"],
                                         "tools": {"fixed": ["Kit-A"]}},
                               # 'beta' grants a reduced multiclass skill (1, from its own list)
                               "beta": {"saving_throws": ["dex", "wis"],
                                        "skills": {"choose": 2, "from": ["Nature", "Arcana"]},
                                        "multiclass": {"skills": {"choose": 1, "from": ["Nature", "Arcana"]},
                                                       "armor": [], "weapons": [], "tools": None}}},
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


def test_missing_save_flagged():
    assert "saving_throws" in _codes(_sheet(["str"], [("Athletics", "class"), ("Stealth", "class")]))  # con missing


def test_extra_save_is_legal():
    # str+con (class) plus dex (e.g. Resilient feat) — an extra save must NOT be flagged.
    assert "saving_throws" not in _codes(
        _sheet(["str", "con", "dex"], [("Athletics", "class"), ("Stealth", "class")]))


def _mc_sheet(class_skills):
    """Multiclass Alpha 5 / Beta 1: Alpha grants 2 skills, Beta's multiclass grant adds 1 (own list)."""
    return {"identity": {"classes": [{"class": "Alpha", "level": 5}, {"class": "Beta", "level": 1}],
                         "background": None},
            "saving_throws": {ab: {"proficient": ab in ("str", "con"), "modifier": 0}
                              for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "skills": {name: {"proficient": True, "source": "class", "expertise": False} for name in class_skills},
            "proficiencies": {"armor": ["Light Armor", "Medium Armor"],
                              "weapons": ["Simple Weapons", "Martial Weapons"], "tools": ["Kit-A"]}}


def test_multiclass_skill_count_ok():
    # 3 class skills = Alpha's 2 + Beta's multiclass 1; all on the combined list → no violation.
    assert proficiencies.check(_mc_sheet(["Athletics", "Stealth", "Nature"]), R) == []


def test_multiclass_skill_count_short():
    codes = {v.code for v in proficiencies.check(_mc_sheet(["Athletics", "Stealth"]), R)}  # only 2, needs 3
    assert "skill_count" in codes


def test_multiclass_skill_off_union():
    # Deception is on neither Alpha's nor Beta's list → off-list even with the union.
    codes = {v.code for v in proficiencies.check(_mc_sheet(["Athletics", "Stealth", "Deception"]), R)}
    assert "skill_off_list" in codes


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


# --- S16: skill-source legality -------------------------------------------------------------------

def test_skill_source_mismatch_background():
    # 'Arcana' claims the background grants it, but the background grants Insight/Religion.
    s = _sheet(["str", "con"], [("Insight", "background"), ("Arcana", "background")], background="Scholar")
    assert "skill_source_mismatch" in _codes(s)


def test_skill_source_missing_when_proficient():
    s = _sheet(["str", "con"], [("Athletics", None)], background="Scholar")   # proficient but source None
    assert "skill_source_missing" in _codes(s)


def test_skill_source_without_proficiency():
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], background="Scholar")
    s["skills"]["skill-x"] = {"proficient": False, "source": "feat", "expertise": False}
    assert "skill_source_without_proficiency" in _codes(s)


def test_feat_sourced_skill_not_flagged():
    # differential: with the check live (a background-sourced non-granted skill DOES mismatch), a
    # feat-sourced skill must NOT — proving the exemption, not a vacuous pass.
    s = _sheet(["str", "con"], [("Insight", "background"), ("Religion", "background"),
                                ("Arcana", "feat"), ("Intimidation", "background")], background="Scholar")
    flagged = [v.actual for v in proficiencies.check(s, R) if v.code == "skill_source_mismatch"]
    assert "Intimidation" in flagged and "Arcana" not in flagged


def test_non_proficient_background_source_not_double_reported():
    # proficient=False + source=background must yield only the advisory, never a mismatch ERROR too.
    s = _sheet(["str", "con"], [("Athletics", "class"), ("Stealth", "class")], background="Scholar")
    s["skills"]["Intimidation"] = {"proficient": False, "source": "background", "expertise": False}
    codes = _codes(s)
    assert "skill_source_without_proficiency" in codes and "skill_source_mismatch" not in codes
