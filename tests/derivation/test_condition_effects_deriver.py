"""Tests for condition-effect consumption in the MODIFIER derivation engine.

Covers the sheet-derivable subset of an active condition's effects: an absolute
speed-zero, a per-level speed penalty, a per-level D20-test penalty, resistance to
all damage, and condition immunities. Read from condition_effect in the DB."""
from app.derivation.modifier import (
    resolve_active_effects, derive_speed, derive_defenses,
)


def _core(**overrides):
    sheet = {
        "identity": {
            "name": "Test", "species": "Species A", "size": "medium",
            "creature_type": "Type A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {"a1": {"final": 14}, "a2": {"final": 16}, "a3": {"final": 12}},
        "proficiency_bonus": 2,
        "saving_throws": {}, "skills": {},
        "permanent_senses": {}, "permanent_speed": {"walk": 30},
        "permanent_defenses": {
            "resistances": [], "immunities": [], "vulnerabilities": [],
            "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
        },
        "proficiencies": {"armor": [], "weapons": [], "tools": []},
        "weapon_masteries": [], "features": [], "feats": [],
        "resource_budgets": {}, "hit_points": {"max": 22},
        "languages": [], "flavour": None,
    }
    sheet.update(overrides)
    return sheet


def _cond_state(state_id, level=None):
    st = {"state": state_id, "source": "environment", "source_type": "condition"}
    if level is not None:
        st["level"] = level
    return st


# ── speed-zero conditions (grappled / restrained) ─────────────────────────────


def test_grappled_zeroes_speed(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("grappled")], [], access)
    assert effects.speed_zero is True
    speeds, _ = derive_speed(core, effects, access)
    assert speeds == {"walk": 0}


def test_restrained_zeroes_speed(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("restrained")], [], access)
    assert effects.speed_zero is True
    speeds, _ = derive_speed(core, effects, access)
    assert speeds == {"walk": 0}


# ── exhaustion: per-level speed + D20 penalties (state id ≠ condition id) ──────


def test_exhaustion_speed_penalty_scales_with_level(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("exhausted", level=3)], [], access)
    assert effects.speed_penalty == 15  # 5 ft × level 3
    speeds, _ = derive_speed(core, effects, access)
    assert speeds["walk"] == 15  # 30 − 15


def test_exhaustion_d20_penalty_scales_with_level(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("exhausted", level=4)], [], access)
    assert effects.d20_penalty == 8  # 2 × level 4


def test_exhaustion_speed_floored_at_zero(access):
    core = _core(permanent_speed={"walk": 10})
    effects = resolve_active_effects(core, None, [_cond_state("exhausted", level=5)], [], access)
    speeds, _ = derive_speed(core, effects, access)
    assert speeds["walk"] == 0  # max(0, 10 − 25)


# ── petrified: resistance to all damage + condition immunity ──────────────────


def test_petrified_grants_resistance_to_all_damage(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("petrified")], [], access)
    from access.validator import defenses as defenses_q
    all_types = set(defenses_q.damage_type_ids(access))
    assert all_types.issubset(effects.resistances)
    defenses = derive_defenses(core, effects, access)
    assert all_types.issubset(set(defenses["resistances"]))


def test_petrified_grants_poisoned_condition_immunity(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_cond_state("petrified")], [], access)
    assert "poisoned" in effects.condition_immunities
    defenses = derive_defenses(core, effects, access)
    assert "poisoned" in defenses["condition_immunities"]


# ── no condition state → no effect ────────────────────────────────────────────


def test_no_condition_state_no_effect(access):
    core = _core()
    effects = resolve_active_effects(core, None, [], [], access)
    assert effects.speed_zero is False
    assert effects.speed_penalty == 0
    assert effects.d20_penalty == 0
