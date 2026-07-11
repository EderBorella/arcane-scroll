"""Tests for the MODIFIER validator."""
from validator.checks.modifier import check
from validator.checks import ALL_CHECKS


def _sheet(**overrides):
    s = {
        "core": {
            "identity": {"size": "medium"},
            "abilities": {
                "a1": {"final": 14},
                "a2": {"final": 16},
                "a3": {"final": 12},
            },
            "proficiency_bonus": 2,
            "saving_throws": {
                "a1": {"proficient": True},
                "a2": {"proficient": False},
                "a3": {"proficient": True},
            },
            "skills": {
                "sk1": {"ability": "a1", "proficient": True, "expertise": False},
                "sk2": {"ability": "a2", "proficient": False, "expertise": False},
            },
            "permanent_defenses": {
                "resistances": ["fire"], "immunities": [], "vulnerabilities": [],
                "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
            },
            "features": [{"name": "Feat A"}],
            "feats": [{"name": "feat-gen"}],
        },
        "inventory": {},
        "grimoire": {"spells": [
            {"name": "Sp3", "source": "class:class-a", "bucket": "prepared"},
        ]},
        "modifier": {
            "schema_version": 1,
            "character_id": "test", "character_name": "Test",
            "xp": 0, "treasure": {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0},
            "hit_points": {"current": 22, "temp": 0, "max_boost": 0, "max_reduction": 0},
            "death_saves": {"successes": 0, "failures": 0},
            "hit_dice": {"d8": {"remaining": 3}},
            "spell_slots": {"1": {"remaining": 4}, "2": {"remaining": 2}},
            "pact_slots": {"1": {"remaining": 0}},
            "resource_state": {"x": {"max": 1, "remaining": 1, "recharge": None, "recharge_amount": None}},
            "abilities": {
                "a1": {"modifier": 2, "reduction": 0},
                "a2": {"modifier": 3, "reduction": 0},
                "a3": {"modifier": 1, "reduction": 0},
            },
            "saving_throws": {
                "a1": {"modifier": 4},
                "a2": {"modifier": 3},
                "a3": {"modifier": 3},
            },
            "skills": {
                "sk1": {"modifier": 4},
                "sk2": {"modifier": 3},
            },
            "passive_scores": {"sk1": 14, "sk2": 13},
            "effective_senses": {"sense-a": 60},
            "effective_defenses": {
                "resistances": ["fire"], "immunities": [], "vulnerabilities": [],
                "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
            },
            "effective_size": "medium",
            "effective_abilities": {"a1": 14, "a2": 16, "a3": 12},
            "armor_class": 13,
            "armor_class_detail": {
                "source": "unarmored", "base": 10, "dex_bonus": 3,
                "bonuses": [], "floor": None,
            },
            "initiative": 3,
            "speed": {"walk": 30},
            "speed_detail": {"base": 30, "base_source": "species", "base_mode": "walk", "modifiers": []},
            "attacks": [],
            "character_states": [],
            "item_states": [],
            "features": [{"name": "Feat A", "uses": {"max": None}}],
            "feats": [{"name": "feat-gen", "uses": {"max": None}}],
            "prepared_spells": [],
        },
    }
    s.update(overrides)
    return s


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ── valid sheet ──────────────────────────────────────────────────────────────


def test_valid_sheet_passes(access):
    assert check(_sheet(), access) == []


# ── AC checks ────────────────────────────────────────────────────────────────


def test_ac_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class"] = 99
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_bonus_duplicate_source(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class_detail"]["bonuses"] = [
        {"value": 2, "source": "spell-ac-1"},
        {"value": 1, "source": "spell-ac-1"},
    ]
    sheet["modifier"]["armor_class"] = 10 + 3 + 2 + 1
    assert "ac-bonus-duplicate-source" in _codes(sheet, access)


def test_ac_bonus_different_source_ok(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class_detail"]["bonuses"] = [
        {"value": 2, "source": "spell-ac-1"},
        {"value": 1, "source": "spell-ac-2"},
    ]
    sheet["modifier"]["armor_class"] = 10 + 3 + 2 + 1
    assert "ac-bonus-duplicate-source" not in _codes(sheet, access)


# ── saving throws ────────────────────────────────────────────────────────────


def test_save_modifier_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["saving_throws"]["a1"]["modifier"] = 99
    assert "save-modifier-mismatch" in _codes(sheet, access)


# ── skills ───────────────────────────────────────────────────────────────────


def test_skill_modifier_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["skills"]["sk1"]["modifier"] = 99
    assert "skill-modifier-mismatch" in _codes(sheet, access)


# ── effective abilities ──────────────────────────────────────────────────────


def test_effective_ability_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["effective_abilities"]["a1"] = 5  # below minimum of 14
    assert "effective-ability-mismatch" in _codes(sheet, access)


def test_effective_ability_above_baseline_ok(access):
    sheet = _sheet()
    sheet["modifier"]["effective_abilities"]["a1"] = 19  # above baseline (set-item), ok
    assert "effective-ability-mismatch" not in _codes(sheet, access)


# ── defenses ─────────────────────────────────────────────────────────────────


def test_defense_missing_core_resistance(access):
    sheet = _sheet()
    sheet["modifier"]["effective_defenses"]["resistances"] = []
    assert "defense-subset-violation" in _codes(sheet, access)


# ── passive scores ───────────────────────────────────────────────────────────


def test_passive_score_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["passive_scores"]["sk1"] = 99
    assert "passive-score-mismatch" in _codes(sheet, access)


# ── features & feats ─────────────────────────────────────────────────────────


def test_missing_feature(access):
    sheet = _sheet()
    sheet["modifier"]["features"] = []
    assert "feature-missing" in _codes(sheet, access)


def test_missing_feat(access):
    sheet = _sheet()
    sheet["modifier"]["feats"] = []
    assert "feat-missing" in _codes(sheet, access)


# ── prepared spells ──────────────────────────────────────────────────────────


def test_prepared_spells_empty_ok(access):
    sheet = _sheet()
    assert "prepared-spells-invalid" not in _codes(sheet, access)


def test_prepared_spells_invalid(access):
    sheet = _sheet()
    sheet["modifier"]["prepared_spells"] = ["nonexistent|class:nonexistent"]
    assert "prepared-spells-invalid" in _codes(sheet, access)


def test_prepared_spells_valid(access):
    sheet = _sheet()
    sheet["modifier"]["prepared_spells"] = ["Sp3|class:class-a"]
    assert "prepared-spells-invalid" not in _codes(sheet, access)


# ── state compatibility ──────────────────────────────────────────────────────


def test_state_incompatible(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [
        {"state": "raging", "source": "test-rage", "source_type": "feature"},
        {"state": "concentrating", "source": "test-spell", "source_type": "spell"},
    ]
    assert "state-incompatible" in _codes(sheet, access)


def test_state_compatible(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [
        {"state": "raging", "source": "test-rage", "source_type": "feature"},
        {"state": "inspired", "source": "test-inspiration", "source_type": "feature"},
    ]
    assert "state-incompatible" not in _codes(sheet, access)


# ── smoke ────────────────────────────────────────────────────────────────────


def test_smoke_not_in_all_checks(access):
    cnames = [c.__module__.split(".")[-1] for c in ALL_CHECKS]
    assert "modifier" not in cnames
