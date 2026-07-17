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


# --------------------------------------------------------------------------- resource budgets (T74)

def test_resource_budgets_from_count_ladder(core_sheet):
    # class-a has a COUNT-ladder resource ('Pool A': 2/3/4 at levels 1/3/5); at level 3 the
    # budget maximum is 3. The BONUS-ladder resource ('Unarmored Movement') is NOT a budget entry.
    budgets = core_sheet["resource_budgets"]
    assert budgets["Pool A"] == {"max": 3}
    assert "Unarmored Movement" not in budgets


def test_resource_budgets_pass_validate_core(core_sheet, access):
    # the independent resource check re-derives the same maximum from the ladder and agrees.
    report = validate_core(core_sheet, access)
    assert report["legal"] is True, report["violations"]


def test_resource_budgets_omitted_when_no_count_ladder(gen_access):
    # a build whose class owns no count-ladder resource carries no resource_budgets block.
    choices = _choices()
    choices["classes"] = [{"class": "class-b", "level": 2}]
    sheet = derive_core(choices, gen_access)
    assert "resource_budgets" not in sheet


def test_resource_budgets_pool_gained_above_level_1(gen_access):
    # a class count-ladder gained above level 1 ('Pool Esc': 1 from level 4, 2 from level 8) is absent
    # below its first ladder level and steps up at its breakpoint (F05-T113 shape).
    choices = _choices()
    choices["classes"] = [{"class": "class-a", "level": 3}]
    assert "Pool Esc" not in derive_core(choices, gen_access).get("resource_budgets", {})
    choices["classes"] = [{"class": "class-a", "level": 4}]
    assert derive_core(choices, gen_access)["resource_budgets"]["Pool Esc"] == {"max": 1}
    choices["classes"] = [{"class": "class-a", "level": 8}]
    assert derive_core(choices, gen_access)["resource_budgets"]["Pool Esc"] == {"max": 2}


# ---------------------------------------------- feat/subclass grant_resource budgets (T114)

def test_resource_budgets_from_feat_grant(gen_access):
    # a feat-owned grant_resource use-pool (always-on) contributes its maximum to the budget.
    choices = _choices()
    choices["feats"] = [{"feat": "feat-res"}]
    budgets = derive_core(choices, gen_access)["resource_budgets"]
    assert budgets["Feat Res Boon"] == {"max": 1}


def test_resource_budgets_from_subclass_grant(gen_access):
    # a subclass-owned grant_resource gained at that class's level 3 is materialised for a level-3 build.
    choices = _choices()
    choices["classes"] = [{"class": "class-a", "level": 3, "subclass": "sub-res"}]
    budgets = derive_core(choices, gen_access)["resource_budgets"]
    assert budgets["Sub Res Power"] == {"max": 1}


def test_subclass_grant_gated_on_class_level_no_multiclass_leak(gen_access):
    # a subclass grant gained at class level 3 must NOT leak into a multiclass build whose sub-res
    # class is only level 2, even though the character's TOTAL level (2 + 5 = 7) is well past 3.
    choices = _choices()
    choices["classes"] = [
        {"class": "class-a", "level": 2, "subclass": "sub-res"},
        {"class": "class-b", "level": 5},
    ]
    sheet = derive_core(choices, gen_access)
    budgets = sheet.get("resource_budgets", {})
    assert "Sub Res Power" not in budgets


# --------------------------------------------------------------------------- class_detail (T76)

def test_class_detail_emitted_from_choice(gen_access):
    # a per-class detail choice is emitted as its display string (consumed downstream by GRIMOIRE).
    choices = _choices()
    choices["classes"] = [{"class": "class-a", "level": 3, "subclass": "sub-a",
                           "class_detail": "do-sch-a"}]
    sheet = derive_core(choices, gen_access)
    assert sheet["identity"]["classes"][0]["class_detail"] == "School A"


def test_class_detail_omitted_when_absent(core_sheet):
    # absent from the choice -> omitted (not serialised as null).
    assert "class_detail" not in core_sheet["identity"]["classes"][0]


# --------------------------------------------------------------------------- class_detail proficiencies (T97)

def _order_choices():
    """A build that picks an order-style class detail (do-order-a) conferring heavy armour + a martial
    weapon tier on top of class-a's own light/medium armour + simple weapons."""
    choices = _choices()
    choices["classes"] = [{"class": "class-a", "level": 3, "subclass": "sub-a",
                           "class_detail": "do-order-a"}]
    return choices


def test_class_detail_proficiencies_materialised(gen_access):
    # the class-detail choice's fixed grants land in the derived proficiency sets.
    sheet = derive_core(_order_choices(), gen_access)
    assert "heavy armor" in sheet["proficiencies"]["armor"]
    assert "martial weapons" in sheet["proficiencies"]["weapons"]


def test_class_detail_proficiencies_absent_without_choice(core_sheet):
    # no order chosen -> the heavier grants are not conferred.
    assert "heavy armor" not in core_sheet["proficiencies"]["armor"]
    assert "martial weapons" not in core_sheet["proficiencies"]["weapons"]


def test_class_detail_proficiency_build_is_legal(gen_access, access):
    # the equip check independently re-derives the class-detail grants, so the build validates.
    report = validate_core(derive_core(_order_choices(), gen_access), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


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


# --------------------------------------------------------------------------- species sub-choices

def _lineage_choices():
    """A species that offers a lineage sub-choice, with the lineage chosen (its id, as the grammar
    offers it). lin-l1 overrides the species darkvision (60 -> 120) and grants a fly speed."""
    return {
        "character_id": "char-l",
        "character_name": "Lineage Build",
        "species": "species-l",
        "lineage": "lin-l1",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8, "wisdom": 10},
        "background_increase": {"a1": 2, "a2": 1},
        "skills": ["sk1", "sk2"],
        "feats": [],
        "languages": [],
    }


def _variant_choices():
    """A species that offers a variant-axis sub-choice, with an option chosen (its name). Variant A
    resolves the species's variant-axis resistance to 'fire'."""
    return {
        "character_id": "char-v",
        "character_name": "Variant Build",
        "species": "species-v",
        "species_variant": "Variant A",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8, "wisdom": 10},
        "background_increase": {"a1": 2, "a2": 1},
        "skills": ["sk1", "sk2"],
        "feats": [],
        "languages": [],
    }


def test_lineage_id_rendered_to_display_name(gen_access):
    sheet = derive_core(_lineage_choices(), gen_access)
    # choices carry the lineage id; CORE renders it to the display name
    assert sheet["identity"]["lineage"] == "Lineage One"


def test_lineage_sense_override_lands(gen_access):
    sheet = derive_core(_lineage_choices(), gen_access)
    # species-l darkvision 60, lin-l1 darkvision 120 -> max wins
    assert sheet["permanent_senses"]["darkvision"] == 120


def test_lineage_speed_grant_lands(gen_access):
    sheet = derive_core(_lineage_choices(), gen_access)
    # the lineage grants a fly speed (sets_total 30); it lands via the identity.lineage owner
    assert sheet["permanent_speed"].get("fly") == 30
    assert sheet["permanent_speed"].get("walk", 0) >= 30


def test_lineage_build_is_legal(gen_access, access):
    report = validate_core(derive_core(_lineage_choices(), gen_access), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


# ------------------------------------------------------------ species/lineage grant_resource (T101/T98)

def test_species_lineage_grant_resources_materialised(gen_access):
    # a level-3 lineage build (PB 2; a1 final 17 -> modifier 3) carries the three grant_resource
    # use-pools with maxima re-derived from each uses_kind:
    #   int -> 1, ability_modifier(a1) -> 3, proficiency_bonus -> 2.
    budgets = derive_core(_lineage_choices(), gen_access)["resource_budgets"]
    assert budgets["Species L Boon"] == {"max": 1}
    assert budgets["Species L Focus"] == {"max": 3}
    assert budgets["Lineage L Power"] == {"max": 2}


def test_grant_resource_budgets_pass_validate_core(gen_access, access):
    # the resources check independently re-derives the same three maxima and agrees.
    report = validate_core(derive_core(_lineage_choices(), gen_access), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


def test_grant_resource_max_wrong_is_flagged(gen_access, access):
    # a proficiency-bonus pool declared with the wrong maximum must be caught (independence proof).
    bad = derive_core(_lineage_choices(), gen_access)
    bad["resource_budgets"]["Lineage L Power"] = {"max": 5}
    report = validate_core(bad, access)
    assert report["legal"] is False
    assert any("Lineage L Power" in v["message"] for v in report["violations"])


def test_variant_resistance_lands(gen_access):
    sheet = derive_core(_variant_choices(), gen_access)
    assert sheet["identity"]["species_variant"] == "Variant A"
    assert "fire" in sheet["permanent_defenses"]["resistances"]


def test_variant_other_option_resolves_differently(gen_access):
    choices = _variant_choices()
    choices["species_variant"] = "Variant B"
    sheet = derive_core(choices, gen_access)
    # Variant B resolves the same axis to a different damage type
    assert "cold" in sheet["permanent_defenses"]["resistances"]
    assert "fire" not in sheet["permanent_defenses"]["resistances"]


def test_variant_build_is_legal(gen_access, access):
    report = validate_core(derive_core(_variant_choices(), gen_access), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


# ------------------------------------------------------------ multi-axis species variants (T100)

def _multi_axis_choices():
    """species-mv offers two independent variant axes; the build picks an option on each. axis-a
    Variant A -> fire, axis-b Variant C -> poison."""
    choices = _variant_choices()
    del choices["species_variant"]
    choices["species"] = "species-mv"
    choices["size"] = "size-a"
    choices["species_variants"] = {"axis-a": "Variant A", "axis-b": "Variant C"}
    return choices


def test_multi_axis_variants_carried(gen_access):
    # both axis picks are recorded without loss.
    sheet = derive_core(_multi_axis_choices(), gen_access)
    assert sheet["identity"]["species_variants"] == {"axis-a": "Variant A", "axis-b": "Variant C"}


def test_multi_axis_each_axis_materialises_its_effect(gen_access):
    # each axis resolves independently to its own resistance.
    resistances = derive_core(_multi_axis_choices(), gen_access)["permanent_defenses"]["resistances"]
    assert "fire" in resistances     # axis-a -> Variant A
    assert "poison" in resistances   # axis-b -> Variant C


def test_multi_axis_other_option_resolves_differently(gen_access):
    choices = _multi_axis_choices()
    choices["species_variants"]["axis-b"] = "Variant D"
    resistances = derive_core(choices, gen_access)["permanent_defenses"]["resistances"]
    assert "fire" in resistances     # axis-a unchanged -> Variant A
    assert "cold" in resistances     # axis-b -> Variant D
    assert "poison" not in resistances


def test_multi_axis_build_is_legal(gen_access, access):
    # the defenses check re-derives each axis independently, so the build validates.
    report = validate_core(derive_core(_multi_axis_choices(), gen_access), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


def test_multi_axis_variants_omitted_when_absent(core_sheet):
    # a species with no variant axes carries neither variant field.
    assert "species_variant" not in core_sheet["identity"]
    assert "species_variants" not in core_sheet["identity"]


def test_no_subchoice_species_omits_fields(gen_access):
    # species-a offers neither sub-choice: the fields are absent from identity
    sheet = derive_core(_choices(), gen_access)
    assert "lineage" not in sheet["identity"]
    assert "species_variant" not in sheet["identity"]
