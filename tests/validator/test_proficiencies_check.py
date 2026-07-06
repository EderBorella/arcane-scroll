from validator.checks.proficiencies import check


def _skill(proficient=True, expertise=False):
    return {"ability": "Ability 1", "proficient": proficient, "expertise": expertise,
            "modifier": 0, "source": "class"}


def _clean_skills():
    # 2 class-pool skills (sk1, sk2 of {sk1,sk2,sk3}), 1 background skill (sk4), all proficient;
    # 1 expertise on a proficient skill (budget: class 2 + background 1 = 3; expertise budget 1)
    return {
        "sk1": _skill(proficient=True, expertise=True),
        "sk2": _skill(proficient=True),
        "sk4": _skill(proficient=True),
    }


def _sheet(skills=None, classes=None, background="Background A", species="Species A", feats=None):
    return {
        "identity": {
            "classes": classes if classes is not None else [{"class": "Class A", "level": 3}],
            "background": background,
            "species": species,
        },
        "feats": feats if feats is not None else [],
        "skills": _clean_skills() if skills is None else skills,
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_proficient_skill_outside_every_source_is_not_legal(access):
    skills = _clean_skills()
    skills["sk6"] = _skill(proficient=True)
    assert "skill-not-legal" in _codes(_sheet(skills), access)


def test_too_many_proficient_skills_over_budget(access):
    # budget is 3 (class 2 + background 1); add sk3 (also class-pool, so still legal) -> 4 total
    skills = _clean_skills()
    skills["sk3"] = _skill(proficient=True)
    codes = _codes(_sheet(skills), access)
    assert "too-many-skill-proficiencies" in codes
    assert "skill-not-legal" not in codes


def test_unresolvable_skill_key_is_unknown(access):
    skills = _clean_skills()
    skills["not-a-skill"] = _skill(proficient=True)
    assert "unknown-skill" in _codes(_sheet(skills), access)


def test_expertise_on_non_proficient_skill(access):
    skills = _clean_skills()
    skills["sk2"]["expertise"] = False
    skills["sk4"]["proficient"] = False
    skills["sk4"]["expertise"] = True
    assert "expertise-not-proficient" in _codes(_sheet(skills), access)


def test_too_many_expertise_over_budget(access):
    # expertise budget is 1 (class-a grants 1 at level 1); mark a second proficient skill as expertise
    skills = _clean_skills()
    skills["sk2"]["expertise"] = True
    assert "too-many-expertise" in _codes(_sheet(skills), access)


def test_malformed_skills_not_a_dict_does_not_raise(access):
    assert "malformed-skills" in _codes(_sheet(skills="x"), access)


def test_species_granted_fixed_skill_is_credited_to_budget(access):
    # full budgeted selection (sk1, sk2 class-pool + sk4 background) plus species-granted sk5
    # (species-a -> sk5, per fixture) must not be flagged as over budget or illegal.
    skills = _clean_skills()
    skills["sk5"] = _skill(proficient=True)
    codes = _codes(_sheet(skills), access)
    assert "too-many-skill-proficiencies" not in codes
    assert "skill-not-legal" not in codes


def test_malformed_identity_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["identity"] = "oops"
    assert isinstance(check(sheet, access), list)


def test_multiclass_secondary_class_skill_grant_is_legal_and_budgeted(access):
    # class-b, taken as the SECOND class, grants sk6 (multiclass_only=1) -- it should widen both
    # the legal universe and the budget, so a sheet proficient in it is fully clean.
    skills = _clean_skills()
    skills["sk6"] = _skill(proficient=True)
    sheet = _sheet(skills, classes=[{"class": "Class A", "level": 3}, {"class": "Class B", "level": 1}])
    codes = _codes(sheet, access)
    assert "skill-not-legal" not in codes
    assert "too-many-skill-proficiencies" not in codes


def test_multiclass_skill_grant_from_a_class_not_taken_is_still_illegal(access):
    # sk6 is only legal via class-b's multiclass grant -- proficient in it WITHOUT class-b in the
    # build is still an illegal skill (a real error must still be caught).
    skills = _clean_skills()
    skills["sk6"] = _skill(proficient=True)
    sheet = _sheet(skills, classes=[{"class": "Class A", "level": 3}])
    assert "skill-not-legal" in _codes(sheet, access)
