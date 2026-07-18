"""Tests for the MODIFIER validator's independent re-derivation of effect-granted attacks (T128).

Content-neutral: the synthetic self-buff spell (Spell Natwep) owns a grant_attack row whose
'spellcasting' ability_mode resolves to class-a's spellcasting ability (a1). The check re-derives
the granted attack from grant_attack — never from the deriver's output."""
from validator.checks.modifier import check


def _sheet(**mod_overrides):
    """A minimal MODIFIER sheet for a class-a caster with an active self-buff granting a natural
    weapon. The granted attack is authored CORRECTLY by default: a1 modifier (2) + PB (2) = 4 to
    hit, 1d6+2 damage, type poison (from the grant row)."""
    core = {
        "identity": {"size": "medium",
                     "classes": [{"class": "Class A", "level": 3, "subclass": None}]},
        "abilities": {"a1": {"final": 14}, "a2": {"final": 16}, "a3": {"final": 12}},
        "proficiency_bonus": 2,
        "saving_throws": {"a1": {"proficient": True}, "a2": {"proficient": False},
                          "a3": {"proficient": True}},
        "skills": {"sk1": {"ability": "a1", "proficient": True, "expertise": False}},
        "permanent_defenses": {"resistances": [], "immunities": [], "vulnerabilities": [],
                               "condition_immunities": [], "save_advantages": [],
                               "condition_advantages": []},
        "features": [], "feats": [],
    }
    modifier = {
        "schema_version": 1, "character_id": "t", "character_name": "T",
        "xp": 0, "treasure": {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0},
        "hit_points": {"current": 22, "temp": 0, "max_boost": 0, "max_reduction": 0},
        "death_saves": {"successes": 0, "failures": 0},
        "hit_dice": {"d8": {"remaining": 3}},
        "spell_slots": {"1": {"remaining": 4}}, "pact_slots": {"1": {"remaining": 0}},
        "resource_state": {},
        "abilities": {"a1": {"modifier": 2, "reduction": 0},
                      "a2": {"modifier": 3, "reduction": 0},
                      "a3": {"modifier": 1, "reduction": 0}},
        "saving_throws": {"a1": {"modifier": 4}, "a2": {"modifier": 3}, "a3": {"modifier": 3}},
        "skills": {"sk1": {"modifier": 4}},
        "passive_scores": {"sk1": 14},
        "effective_senses": {},
        "effective_defenses": {"resistances": [], "immunities": [], "vulnerabilities": [],
                               "condition_immunities": [], "save_advantages": [],
                               "condition_advantages": []},
        "effective_size": "medium",
        "effective_abilities": {"a1": 14, "a2": 16, "a3": 12},
        "armor_class": 13,
        "armor_class_detail": {"source": "unarmored", "base": 10, "dex_bonus": 3,
                               "bonuses": [], "floor": None},
        "initiative": 3, "speed": {"walk": 30},
        "speed_detail": {"base": 30, "base_source": "species", "base_mode": "walk", "modifiers": []},
        "attacks": [{"name": "Attack Alpha", "attack_bonus": 4, "damage": "1d6+2",
                     "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        "character_states": [{"state": "altered", "source": "Spell Natwep", "source_type": "spell",
                              "detail": {"option": "natural_weapons"}}],
        "item_states": [],
        "features": [], "feats": [], "prepared_spells": [],
    }
    modifier.update(mod_overrides)
    return {"core": core, "inventory": {}, "grimoire": {"spells": []}, "modifier": modifier}


def _granted_codes(sheet, access):
    return {v.code for v in check(sheet, access) if v.code.startswith("granted-attack")}


def test_correct_granted_attack_passes(access):
    assert _granted_codes(_sheet(), access) == set()


def test_missing_granted_attack_flagged(access):
    sheet = _sheet(attacks=[])
    assert "granted-attack-missing" in _granted_codes(sheet, access)


def test_wrong_attack_bonus_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["attack_bonus"] = 99
    assert "granted-attack-bonus-mismatch" in _granted_codes(sheet, access)


def test_wrong_damage_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["damage"] = "1d6+99"
    assert "granted-attack-damage-mismatch" in _granted_codes(sheet, access)


def test_wrong_damage_type_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["damage_type"] = "fire"
    assert "granted-attack-type-mismatch" in _granted_codes(sheet, access)


def test_no_state_no_granted_attack_check(access):
    """With no active state the granted-attack check is inert (no owner to read a grant from)."""
    sheet = _sheet(character_states=[], attacks=[])
    assert _granted_codes(sheet, access) == set()
