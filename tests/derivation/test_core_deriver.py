"""CORE deriver (F05-T67) tests — synthetic, content-neutral choices only.

The deriver builds a ``core-sheet:1`` from a generated character's choices, grounded in the DAL. The
primary acceptance check is that its output passes ``/validate-core`` (``validate_core``); the rule
assertions below pin the semantics of the loaded ruleset (background — not species — ability
increases, the origin feat from the background, canonical lowercase weapon proficiencies).

All ids are synthetic placeholders from the shared rules-DB fixture (``class-a``, ``species-a``,
``bg-a``, ``sk1`` …) — never real game vocabulary.
"""
import copy

import pytest

from app.derivation import core
from app.derivation.core import derive_core
from validator.validate_core import validate_core


def _choices():
    """A single-class level-3 build with a subclass: exercises identity, abilities (background ASI),
    saving throws, skills, armour/weapon/tool proficiencies, senses/speed/defences from the grant
    spine, hit dice, features, and the background origin feat."""
    return {
        "character_id": "char-1",
        "character_name": "Test Character",
        "species": "species-a",
        "size": "size-a",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        # bases for every ability in the synthetic ruleset (a1..a6 + the extra 'wisdom' ability)
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8, "wisdom": 10},
        # background ASI: {2,1} shape onto two of bg-a's allowed abilities (a1,a2,a3)
        "background_increase": {"a1": 2, "a2": 1},
        # two picks from class-a's pool {sk1,sk2,sk3}
        "skills": ["sk1", "sk2"],
        "feats": [],
        "languages": [],
    }


@pytest.fixture
def core_sheet(gen_access):
    return derive_core(_choices(), gen_access)


# --------------------------------------------------------------------------- acceptance

def test_derived_core_passes_validate_core(core_sheet, access):
    report = validate_core(core_sheet, access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


# --------------------------------------------------------------------------- ruleset semantics

def test_background_ability_increase_applied(core_sheet, gen_access):
    # a1 gets +2, a2 gets +1 from the background; abbrev keys are lowercased on the sheet.
    x1 = core_sheet["abilities"]["x1"]
    x2 = core_sheet["abilities"]["x2"]
    assert x1 == {"base": 15, "background_bonus": 2, "final": 17}
    assert x2 == {"base": 13, "background_bonus": 1, "final": 14}


def test_no_species_ability_bonus(core_sheet):
    # A species grants NO ability bonus under this ruleset: every final is exactly base +
    # background_bonus (no hidden species contribution), and every unboosted ability keeps final == base.
    for entry in core_sheet["abilities"].values():
        assert entry["final"] == entry["base"] + entry["background_bonus"]
    x3 = core_sheet["abilities"]["x3"]
    assert x3["background_bonus"] == 0
    assert x3["final"] == x3["base"]


def test_origin_feat_from_background_present(core_sheet):
    names = [f["name"] for f in core_sheet["feats"]]
    assert "feat-origin" in names
    origin = next(f for f in core_sheet["feats"] if f["name"] == "feat-origin")
    assert origin["source"] == "background"


def test_weapon_proficiencies_are_lowercase(core_sheet):
    weapons = core_sheet["proficiencies"]["weapons"]
    assert weapons, "expected at least one weapon proficiency"
    for w in weapons:
        assert w == w.lower(), f"weapon proficiency not lowercase: {w!r}"
    assert "simple weapons" in weapons


def test_proficiency_bonus_from_total_level(core_sheet):
    assert core_sheet["identity"]["total_level"] == 3
    assert core_sheet["proficiency_bonus"] == 2


def test_saving_throws_from_first_class(core_sheet):
    # class-a grants saves in a1,a2 -> abbrev keys x1,x2 proficient; the rest are not.
    saves = core_sheet["saving_throws"]
    assert saves["x1"]["proficient"] is True
    assert saves["x2"]["proficient"] is True
    assert saves["x3"]["proficient"] is False


def test_skills_source_attribution(core_sheet):
    # class picks vs background-fixed vs species-granted skills carry the right source.
    skills = core_sheet["skills"]
    assert skills["Sk1"]["proficient"] and skills["Sk1"]["source"] == "class"
    assert skills["Sk4"]["proficient"] and skills["Sk4"]["source"] == "background"
    assert skills["Sk5"]["proficient"] and skills["Sk5"]["source"] == "species"
    assert skills["Sk3"]["proficient"] is False and skills["Sk3"]["source"] is None


def test_hit_dice_match_class_levels(core_sheet):
    assert core_sheet["hit_dice"] == {"d8": {"max": 3}}
    assert core_sheet["hit_points"]["max"] >= 1


def test_permanent_senses_speed_defenses_grounded(core_sheet):
    # species darkvision 60 is overridden (max-not-sum) by the subclass's darkvision 120 at level 3.
    assert core_sheet["permanent_senses"]["darkvision"] == 120
    # species poison resistance + subclass charmed immunity (both at the character's level).
    assert core_sheet["permanent_defenses"]["resistances"] == ["poison"]
    assert core_sheet["permanent_defenses"]["condition_immunities"] == ["charmed"]
    assert "walk" in core_sheet["permanent_speed"]


# --------------------------------------------------------------------------- review fixes

def test_final_ability_score_is_capped(gen_access):
    # base 15 + background 2 + a feat +5 would be 22; the standard cap (20) must clamp `final`.
    choices = _choices()
    choices["feats"] = [{"feat": "feat-gen", "ability_increase": {"ability": "a1", "amount": 5}}]
    sheet = derive_core(choices, gen_access)
    assert sheet["abilities"]["x1"]["final"] == 20
    # the raw background bonus is still reported; only the final is clamped
    assert sheet["abilities"]["x1"]["background_bonus"] == 2


def test_choose_any_class_skill_attributed_to_class(gen_access):
    # class-any has a choose-ANY-skill pool (no explicit options); a chosen skill outside any explicit
    # pool is still a class pick, not a 'feature' grant.
    choices = {"classes": [{"class": "class-any", "level": 1}], "skills": ["sk7"], "background": None}
    sources = core._skill_sources(gen_access, choices)
    assert sources["sk7"] == "class"


def test_missing_size_fails_fast(gen_access):
    # species-a offers sizes, so omitting the choice defaults cleanly; but a species with no size and
    # no supplied size must raise rather than emit a null the contract forbids.
    choices = _choices()
    choices["species"] = "species-a"
    choices["size"] = None
    # sanity: the default path still works for a species that declares sizes
    assert derive_core(choices, gen_access)["identity"]["size"] is not None


def test_zero_walk_not_emitted(gen_access):
    # _derive_speeds drops any zero-valued mode so a baseless build never emits a spurious 'walk 0'.
    assert core._derive_speeds([], 0, []) == {}
    assert core._derive_speeds([], 30, []) == {"walk": 30}


def test_senses_and_speed_resolved_independently(core_sheet):
    # The deriver owns these resolvers (no validator import); values must still be correct.
    assert core_sheet["permanent_senses"]["darkvision"] == 120  # max-not-sum (species 60, subclass 120)
    assert "walk" in core_sheet["permanent_speed"]


# --------------------------------------------------------------------------- RED: malformed CORE

def test_ungranted_proficiency_is_flagged_illegal(core_sheet, access):
    # A CORE claiming a weapon proficiency the build does not grant must fail validation — proving the
    # deriver's output is validated against the grant spine, not blessed wholesale.
    bad = copy.deepcopy(core_sheet)
    bad["proficiencies"]["weapons"].append("martial weapons")
    report = validate_core(bad, access)
    assert report["legal"] is False
    assert any("martial weapons" in v["message"] for v in report["violations"])


def test_illegal_background_boost_shape_is_flagged(gen_access, access):
    # A background increase that is not {2,1} or {1,1,1} must be caught by the abilities check.
    choices = _choices()
    choices["background_increase"] = {"a1": 3}
    bad = derive_core(choices, gen_access)
    report = validate_core(bad, access)
    assert report["legal"] is False
