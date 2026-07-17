"""Tests for self-transform full effective-stat replacement in MODIFIER (F05-T60).

Content-neutral: synthetic creatures only. ``creature-form`` is a CONCRETE form carrying a
mental ability score ('wisdom') so the retained-vs-replaced split can be exercised; ``creature-t``
is templated (formula-scaled). Both the deriver (form-block replacement) and the validator
(independent re-derivation + retained-mental enforcement) are covered.
"""
from app.derivation.modifier import (
    ActiveEffects, _accumulate_transform,
    derive_abilities, derive_ac, derive_speed, derive_senses,
    derive_defenses, derive_saving_throws, derive_skills,
    TRANSFORM_PHYSICAL, TRANSFORM_FULL,
)
from validator.checks.modifier import check


# ── deriver: transform capture (concrete vs templated vs legacy size-only) ────


def _tf_state(into, transform=None):
    detail = {"into": into}
    if transform is not None:
        detail["transform"] = transform
    return {"state": "shaped", "source": "Spell-Grow", "source_type": "spell", "detail": detail}


def test_accumulate_transform_concrete_sets(access):
    eff = ActiveEffects()
    _accumulate_transform(eff, access, _tf_state("creature-form", "physical"))
    assert eff.transform == {"creature_id": "creature-form", "kind": "physical"}


def test_accumulate_transform_templated_skipped(access):
    eff = ActiveEffects()
    _accumulate_transform(eff, access, _tf_state("creature-t", "full"))
    assert eff.transform is None


def test_accumulate_transform_unknown_skipped(access):
    eff = ActiveEffects()
    _accumulate_transform(eff, access, _tf_state("no-such-creature", "physical"))
    assert eff.transform is None


def test_accumulate_transform_missing_kind_is_legacy_size_only(access):
    """`detail.into` with no `transform` kind stays legacy size-only (no full replacement)."""
    eff = ActiveEffects()
    _accumulate_transform(eff, access, _tf_state("creature-form"))
    assert eff.transform is None


# ── deriver: ability replacement (physical retains mental, full replaces all) ─


def _core_abilities():
    return {"abilities": {"a1": {"final": 14}, "a2": {"final": 16},
                          "a3": {"final": 12}, "wis": {"final": 10}}}


def test_derive_abilities_physical_retains_mental(access):
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form", "kind": TRANSFORM_PHYSICAL}
    _, effective, _ = derive_abilities(_core_abilities(), eff, access)
    # physical abilities replaced by the form; mental (wis) retained from the character
    assert effective["a1"] == 18
    assert effective["a2"] == 6
    assert effective["a3"] == 14
    assert effective["wis"] == 10


def test_derive_abilities_full_replaces_mental(access):
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form", "kind": TRANSFORM_FULL}
    _, effective, _ = derive_abilities(_core_abilities(), eff, access)
    assert effective["a1"] == 18
    assert effective["wis"] == 8  # mental replaced under FULL


def test_derive_ac_speed_senses_defenses_from_form(access):
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form", "kind": TRANSFORM_PHYSICAL}
    ac, detail = derive_ac({}, {}, eff, {}, access)
    assert ac == 15 and detail["source"] == "creature-form" and detail["dex_bonus"] == 0
    speeds, _ = derive_speed({}, eff, access)
    assert speeds == {"walk": 40, "climb": 20}
    assert derive_senses({}, eff, access) == {"darkvision": 120}
    # form defences are authoritative: the form's 'cold' resistance, not any CORE resistance
    assert derive_defenses({"permanent_defenses": {"resistances": ["fire"]}}, eff, access)[
        "resistances"] == ["cold"]


def test_derive_saving_throws_full_drops_proficiency(access):
    """Under FULL the saves are the form's ability modifiers with no character proficiency/PB."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form", "kind": TRANSFORM_FULL}
    core = {"saving_throws": {"a1": {"proficient": True}}}
    ability_mods = {"a1": 4}
    saves = derive_saving_throws(core, ability_mods, 3, eff, access)
    assert saves["a1"]["modifier"] == 4  # no +PB even though CORE marks it proficient


# ── deriver: T65 higher-of + gained form proficiencies (save/skill) ───────────


def _sp_core():
    return {
        "abilities": {"a1": {"final": 14}, "a2": {"final": 16},
                      "a3": {"final": 12}, "wis": {"final": 10}},
        "saving_throws": {},   # character proficient in no save
        "skills": {"sk1": {"ability": "a1", "proficient": False, "expertise": False}},
    }


def test_physical_save_takes_higher_of_form(access):
    """PHYSICAL: the form's proficiency-inclusive save (wisdom +8) beats the character's own
    (retained wisdom mod 0, not proficient) — the higher-of picks the form."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_PHYSICAL}
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 0}
    saves = derive_saving_throws(_sp_core(), ability_mods, 2, eff, access)
    assert saves["wis"]["modifier"] == 8    # max(own 0, form 4+pb4)
    assert saves["a1"]["modifier"] == 4     # own == form (both +4, neither proficient)


def test_physical_skill_takes_higher_of_form(access):
    """PHYSICAL: the form's skill bonus (sk1 = 9) beats the character's own (+4, not proficient)."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_PHYSICAL}
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 0}
    skills = derive_skills(_sp_core(), ability_mods, 2, eff, access)
    assert skills["sk1"]["modifier"] == 9


def test_full_save_uses_form_proficiency(access):
    """FULL: the form's stat block is authoritative — the form's save proficiency (its own PB)
    applies (wisdom = form mod 4 + form pb 4 = 8), with no character proficiency."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_FULL}
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 4}
    saves = derive_saving_throws(_sp_core(), ability_mods, 2, eff, access)
    assert saves["wis"]["modifier"] == 8    # form proficiency, form PB
    assert saves["a1"]["modifier"] == 4     # form not proficient in a1


def test_full_skill_uses_form_skill_bonus(access):
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_FULL}
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 4}
    skills = derive_skills(_sp_core(), ability_mods, 2, eff, access)
    assert skills["sk1"]["modifier"] == 9   # form's stat-block skill bonus


def test_physical_gains_form_save_proficiency_with_own_pb(access):
    """Book rule: a PHYSICAL transform GAINS the form's save proficiencies and applies the
    character's OWN PB to them, then takes the higher of that and the form's stat block. A high
    retained wisdom + high own PB beats the form's own (lower-PB) wisdom save — distinguishing the
    correct rule from a plain higher-of that ignores the gained own-PB proficiency."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_PHYSICAL}
    core = {"saving_throws": {}}                 # character proficient in NO save of their own
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 6}
    saves = derive_saving_throws(core, ability_mods, 4, eff, access)
    # gained wisdom proficiency, own PB: 6 + 4 = 10, higher than the form's stat-block save (8)
    assert saves["wis"]["modifier"] == 10


def test_physical_gains_form_skill_proficiency_with_own_pb(access):
    """PHYSICAL transform gains the form's skill proficiency with the character's OWN PB, then
    higher-of the form's stat-block bonus."""
    eff = ActiveEffects()
    eff.transform = {"creature_id": "creature-form-sp", "kind": TRANSFORM_PHYSICAL}
    core = {"skills": {"sk1": {"ability": "a1", "proficient": False, "expertise": False}}}
    ability_mods = {"a1": 4, "a2": -2, "a3": 2, "wis": 0}
    skills = derive_skills(core, ability_mods, 6, eff, access)
    # gained sk1 proficiency, own PB: 4 + 6 = 10, higher than the form's stat-block bonus (9)
    assert skills["sk1"]["modifier"] == 10


# ── validator: routing + independent re-derivation + retained-mental split ────


def _transform_sheet(kind, **mod_over):
    """A coherent transformed MODIFIER sheet for creature-form under `kind`, ready to mutate."""
    wis = 8 if kind == TRANSFORM_FULL else 10
    wis_mod = (wis - 10) // 2
    modifier = {
        "abilities": {"a1": {"modifier": 4, "reduction": 0},
                      "a2": {"modifier": -2, "reduction": 0},
                      "a3": {"modifier": 2, "reduction": 0},
                      "wis": {"modifier": wis_mod, "reduction": 0}},
        "effective_abilities": {"a1": 18, "a2": 6, "a3": 14, "wis": wis},
        "saving_throws": {"a1": {"modifier": 4}},
        "skills": {"sk1": {"modifier": 4}},
        "passive_scores": {"sk1": 14},
        "effective_senses": {"darkvision": 120},
        "effective_defenses": {"resistances": ["cold"], "immunities": [],
                               "vulnerabilities": [], "condition_immunities": [],
                               "save_advantages": [], "condition_advantages": []},
        "effective_size": "size-a",
        "armor_class": 15,
        "armor_class_detail": {"source": "creature-form", "base": 15, "dex_bonus": 0,
                               "bonuses": [], "floor": None},
        "hit_points": {"current": 20, "temp": 20, "max_boost": 0, "max_reduction": 0},
        "speed": {"walk": 40, "climb": 20},
        "attacks": [{"name": "Strike A", "attack_bonus": 6, "damage": "2d6 + 4",
                     "damage_type": "slashing", "weapon_mastery": None, "properties": []}],
        "features": [{"name": "Feat A", "uses": {"max": None}}],
        "feats": [{"name": "feat-gen", "uses": {"max": None}}],
        "prepared_spells": [],
        "character_states": [
            {"state": "shaped", "source": "Spell-Grow", "source_type": "spell",
             "detail": {"into": "creature-form", "transform": kind}}],
        "item_states": [],
    }
    modifier.update(mod_over)
    return {
        "core": {
            "identity": {"size": "size-a"},
            "abilities": {"a1": {"final": 14}, "a2": {"final": 16},
                          "a3": {"final": 12}, "wis": {"final": 10}},
            "proficiency_bonus": 2,
            "saving_throws": {"a1": {"proficient": False}},
            "skills": {"sk1": {"ability": "a1", "proficient": False, "expertise": False}},
            "permanent_defenses": {"resistances": ["fire"], "immunities": [],
                                   "vulnerabilities": [], "condition_immunities": [],
                                   "save_advantages": [], "condition_advantages": []},
            "features": [{"name": "Feat A"}],
            "feats": [{"name": "feat-gen"}],
        },
        "inventory": {},
        "grimoire": {},
        "modifier": modifier,
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_transform_physical_correct_passes(access):
    codes = _codes(_transform_sheet(TRANSFORM_PHYSICAL), access)
    assert not any(c.startswith("transform-") for c in codes), codes


def test_transform_full_correct_passes(access):
    codes = _codes(_transform_sheet(TRANSFORM_FULL), access)
    assert not any(c.startswith("transform-") for c in codes), codes


def test_transform_wrong_physical_ability_flagged(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["effective_abilities"]["a1"] = 14  # kept the character's, not the form's 18
    assert "transform-ability-mismatch" in _codes(sheet, access)


def test_transform_retained_mental_enforced(access):
    """A physical transform must RETAIN the character's mental ability, not take the form's."""
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["effective_abilities"]["wis"] = 8   # the form's wisdom (wrong: must retain 10)
    sheet["modifier"]["abilities"]["wis"]["modifier"] = -1
    assert "transform-ability-mismatch" in _codes(sheet, access)


def test_transform_full_mental_must_be_form(access):
    """Under FULL, keeping the character's mental score is wrong — must be the form's."""
    sheet = _transform_sheet(TRANSFORM_FULL)
    sheet["modifier"]["effective_abilities"]["wis"] = 10  # the character's (wrong under FULL)
    sheet["modifier"]["abilities"]["wis"]["modifier"] = 0
    assert "transform-ability-mismatch" in _codes(sheet, access)


def test_transform_wrong_ac_flagged(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["armor_class"] = 18
    sheet["modifier"]["armor_class_detail"]["base"] = 18
    assert "transform-ac-mismatch" in _codes(sheet, access)


def test_transform_wrong_speed_flagged(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["speed"] = {"walk": 30}
    assert "transform-speed-mismatch" in _codes(sheet, access)


def test_transform_defenses_form_authoritative(access):
    """Retaining the character's CORE resistance instead of the form's is flagged (replace-not-union)."""
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["effective_defenses"]["resistances"] = ["fire"]  # CORE's, not the form's cold
    assert "transform-defense-mismatch" in _codes(sheet, access)


def test_transform_wrong_form_attack_flagged(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["attacks"][0]["attack_bonus"] = 3   # form's Strike A is +6
    assert "transform-attack-mismatch" in _codes(sheet, access)


def test_transform_missing_form_attack_flagged(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["attacks"] = []   # the form's Strike A action is not materialised
    assert "transform-attack-missing" in _codes(sheet, access)


def test_transform_templated_form_rejected(access):
    sheet = _transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["character_states"][0]["detail"]["into"] = "creature-t"
    assert "transform-templated-not-form" in _codes(sheet, access)


# ── validator: T65 higher-of + gained form proficiencies (save/skill) ─────────


def _sp_transform_sheet(kind):
    """A coherent transformed MODIFIER sheet for creature-form-sp (save + skill proficient),
    with saves/skills at the correct higher-of / form values, ready to mutate."""
    wis = 18 if kind == TRANSFORM_FULL else 10
    wis_mod = (wis - 10) // 2
    wis_save = 8    # PHYSICAL: max(own 0, form 8); FULL: form 8 — both 8
    modifier = {
        "abilities": {"a1": {"modifier": 4, "reduction": 0},
                      "a2": {"modifier": -2, "reduction": 0},
                      "a3": {"modifier": 2, "reduction": 0},
                      "wis": {"modifier": wis_mod, "reduction": 0}},
        "effective_abilities": {"a1": 18, "a2": 6, "a3": 14, "wis": wis},
        "saving_throws": {"a1": {"modifier": 4}, "a2": {"modifier": -2},
                          "a3": {"modifier": 2}, "wis": {"modifier": wis_save}},
        "skills": {"sk1": {"modifier": 9}},
        "passive_scores": {"sk1": 19},
        "effective_senses": {},
        "effective_defenses": {"resistances": [], "immunities": [],
                               "vulnerabilities": [], "condition_immunities": [],
                               "save_advantages": [], "condition_advantages": []},
        "effective_size": "size-a",
        "armor_class": 14,
        "armor_class_detail": {"source": "creature-form-sp", "base": 14, "dex_bonus": 0,
                               "bonuses": [], "floor": None},
        "hit_points": {"current": 20, "temp": 0, "max_boost": 0, "max_reduction": 0},
        "speed": {"walk": 40},
        "attacks": [{"name": "Strike A", "attack_bonus": 6, "damage": "2d6 + 4",
                     "damage_type": "slashing", "weapon_mastery": None, "properties": []}],
        "features": [], "feats": [], "prepared_spells": [],
        "character_states": [
            {"state": "shaped", "source": "Spell-Grow", "source_type": "spell",
             "detail": {"into": "creature-form-sp", "transform": kind}}],
        "item_states": [],
    }
    return {
        "core": {
            "identity": {"size": "size-a"},
            "abilities": {"a1": {"final": 14}, "a2": {"final": 16},
                          "a3": {"final": 12}, "wis": {"final": 10}},
            "proficiency_bonus": 2,
            "saving_throws": {"a1": {"proficient": False}, "a2": {"proficient": False},
                              "a3": {"proficient": False}, "wis": {"proficient": False}},
            "skills": {"sk1": {"ability": "a1", "proficient": False, "expertise": False}},
            "permanent_defenses": {"resistances": [], "immunities": [],
                                   "vulnerabilities": [], "condition_immunities": [],
                                   "save_advantages": [], "condition_advantages": []},
            "features": [], "feats": [],
        },
        "inventory": {}, "grimoire": {},
        "modifier": modifier,
    }


def test_physical_higher_of_save_passes(access):
    codes = _codes(_sp_transform_sheet(TRANSFORM_PHYSICAL), access)
    assert not any(c in ("save-modifier-mismatch", "skill-modifier-mismatch") for c in codes), codes


def test_physical_save_own_instead_of_form_flagged(access):
    """Using the character's own (lower) wisdom save instead of the higher form value is illegal."""
    sheet = _sp_transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["saving_throws"]["wis"]["modifier"] = 0   # own retained wis, not higher-of
    assert "save-modifier-mismatch" in _codes(sheet, access)


def test_physical_skill_own_instead_of_form_flagged(access):
    sheet = _sp_transform_sheet(TRANSFORM_PHYSICAL)
    sheet["modifier"]["skills"]["sk1"]["modifier"] = 4          # own, not the form's 9
    assert "skill-modifier-mismatch" in _codes(sheet, access)


def test_full_form_proficiency_save_passes(access):
    codes = _codes(_sp_transform_sheet(TRANSFORM_FULL), access)
    assert not any(c in ("save-modifier-mismatch", "skill-modifier-mismatch") for c in codes), codes


def test_full_save_without_form_proficiency_flagged(access):
    """Under FULL the form's save proficiency applies; dropping it (wisdom = form mod only) is illegal."""
    sheet = _sp_transform_sheet(TRANSFORM_FULL)
    sheet["modifier"]["saving_throws"]["wis"]["modifier"] = 4   # form mod without the form's PB
    assert "save-modifier-mismatch" in _codes(sheet, access)


def test_physical_gained_save_uses_own_pb(access):
    """Book rule: a save the FORM is proficient in but the character is not — the character GAINS
    the proficiency and applies their OWN (higher) PB, then higher-of vs the form's stat block. A
    high retained wisdom (mod +6) with own PB 4 => 10, beating the form's 8."""
    sheet = _sp_transform_sheet(TRANSFORM_PHYSICAL)
    sheet["core"]["abilities"]["wis"] = {"final": 22}          # retained high wisdom (mod +6)
    sheet["core"]["proficiency_bonus"] = 4
    sheet["modifier"]["abilities"]["wis"] = {"modifier": 6, "reduction": 0}
    sheet["modifier"]["effective_abilities"]["wis"] = 22
    sheet["modifier"]["saving_throws"]["wis"]["modifier"] = 10  # gained prof + own PB
    assert "save-modifier-mismatch" not in _codes(sheet, access)
    # taking only the form's stat-block value (8), i.e. not applying the character's own PB, is wrong
    sheet["modifier"]["saving_throws"]["wis"]["modifier"] = 8
    assert "save-modifier-mismatch" in _codes(sheet, access)
