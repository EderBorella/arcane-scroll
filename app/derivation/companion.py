"""COMPANION derivation — concrete-creature slice.

Pure functions that compute a ``companionModifier`` (companion-modifier:1 shape)
from a catalogued creature's FIXED statblock, read straight from the creature
catalog via ``access.validator.creature``. No orchestrator, no non-overwritable
protection, no session-state merge — those live in ``companion_orchestrator``.

Scope: this slice handles only NON-TEMPLATED creatures — those whose stats are
stored directly (a fixed statblock read verbatim from the catalog). Templated
creatures — those carrying ``creature_formula`` rows whose block scales with the
owner's spell level / stats — are deferred to the scaling phase (P2). They are
detected here (:func:`is_templated`) and only STUBBED (a minimal contract-valid
block) so the shape holds; their real, formula-scaled derivation slots in later.
"""
import re

from access.validator import creature as creature_q

# Canonical ability-id order for a stable saving-throws emission.
_ABILITY_ORDER = (
    "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma",
)


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ability_mod(score: int) -> int:
    return (score - 10) // 2


def is_templated(access, creature_id: str) -> bool:
    """True when a creature's block is formula-scaled (carries creature_formula rows).

    Such creatures are deferred to the scaling phase; this slice only stubs them.
    """
    return bool(creature_q.creature_formulas(access, creature_id))


# ── per-field readers (fixed-stat creatures) ─────────────────────────────────


def _hit_dice(hp_dice) -> dict:
    """Parse the leading ``NdM`` of a creature's HP-dice expression into a hit-dice
    table ``{"dM": {"max": N, "remaining": N}}``. A fresh block starts full, so
    remaining == max. Returns {} when no dice term is present."""
    if not isinstance(hp_dice, str):
        return {}
    m = re.search(r"(\d+)\s*d\s*(\d+)", hp_dice)
    if not m:
        return {}
    count, faces = int(m.group(1)), int(m.group(2))
    return {f"d{faces}": {"max": count, "remaining": count}}


def _ability_scores(access, creature_id: str) -> dict:
    return {r["ability_id"]: r["score"]
            for r in creature_q.creature_abilities(access, creature_id)
            if _int(r["score"])}


def _speed(access, creature_id: str) -> dict:
    """Effective movement modes keyed by mode id → feet. A mode stored as a
    formula_note ('equal to its Walk Speed') resolves to the walk value."""
    rows = creature_q.creature_speeds(access, creature_id)
    walk = None
    for r in rows:
        if r["movement_mode_id"] == "walk" and _int(r["feet"]):
            walk = r["feet"]
    result = {}
    for r in rows:
        mode, feet = r["movement_mode_id"], r["feet"]
        if _int(feet):
            result[mode] = feet
        elif r["formula_note"] and walk is not None:
            result[mode] = walk
    return result


def _senses(access, creature_id: str) -> dict:
    return {r["sense_id"]: r["range_ft"]
            for r in creature_q.creature_senses(access, creature_id)
            if _int(r["range_ft"])}


def _skills(access, creature_id: str) -> list:
    return [{"name": r["skill_id"], "bonus": r["bonus"]}
            for r in creature_q.creature_skills(access, creature_id)
            if _int(r["bonus"])]


def _saving_throws(access, creature_id: str) -> list:
    """Re-derive each save from the creature's own facts: ability modifier plus the
    creature's proficiency bonus for a proficient save. Creatures store ``pb``
    directly; the catalog carries NO creature save-proficiency table, so with no
    proficiency data every save is exactly its ability modifier. (This is a
    deliberate creature-shaped re-derivation, NOT the character-shaped MODIFIER
    saves helper.)"""
    scores = {r["ability_id"]: r["score"]
              for r in creature_q.creature_abilities(access, creature_id)
              if _int(r["score"])}
    ordered = [a for a in _ABILITY_ORDER if a in scores]
    ordered += [a for a in scores if a not in _ABILITY_ORDER]
    return [{"ability": aid, "modifier": _ability_mod(scores[aid])} for aid in ordered]


def _defenses(access, creature_id: str) -> dict | None:
    """A companion's defence block, or None when the creature has no defences.
    Resistances/immunities(damage+condition)/vulnerabilities, straight from the
    catalog rows."""
    d = creature_q.creature_defenses(access, creature_id)
    resistance = [r["damage_type_id"] for r in d["resistance"] if r["damage_type_id"]]
    imm_damage = [r["damage_type_id"] for r in d["immunity_damage"] if r["damage_type_id"]]
    imm_condition = [r["condition_id"] for r in d["immunity_condition"] if r["condition_id"]]
    vulnerability = [r["damage_type_id"] for r in d["vulnerability"] if r["damage_type_id"]]
    if not (resistance or imm_damage or imm_condition or vulnerability):
        return None
    return {
        "resistance": resistance,
        "immunity": {"damage": imm_damage, "condition": imm_condition},
        "vulnerability": vulnerability,
    }


def _attacks(access, creature_id: str) -> list:
    """Attack entries from the creature's action rows. An action counts as an attack
    when it carries an attack bonus; its damage string is the stored dice
    expression, or the flat average when no dice term is stored."""
    result = []
    for row in creature_q.creature_actions(access, creature_id):
        atk_bonus = row["atk_bonus"]
        if not _int(atk_bonus):
            continue
        dmg_dice = row["dmg_dice"]
        if isinstance(dmg_dice, str) and dmg_dice.strip():
            damage = dmg_dice.strip()
        elif _int(row["dmg_average"]):
            damage = str(row["dmg_average"])
        else:
            damage = None
        result.append({
            "name": row["name"],
            "attack_bonus": atk_bonus,
            "damage": damage,
            "damage_type": row["damage_type_id"],
        })
    return result


# ── per-companion derivation ─────────────────────────────────────────────────


def _base_hp(row) -> int:
    hp = row["hp_average"]
    return hp if _int(hp) else 0


def derive_concrete(access, companion_index: int, creature_id: str, row) -> dict:
    """Derive a full companionModifier for one fixed-stat creature. Asserts the
    contract-required ``hit_points`` and ``speed`` are present."""
    hp_max = _base_hp(row)
    speed = _speed(access, creature_id)
    if not speed:
        # A catalogued creature should always carry at least a walk speed; guard the
        # contract's minProperties:1 so a data gap can't produce an invalid block.
        speed = {"walk": 0}

    modifier = {
        "companion_index": companion_index,
        "ability_scores": _ability_scores(access, creature_id),
        "hit_points": {"max": hp_max, "current": hp_max, "temp": 0},
        "hit_dice": _hit_dice(row["hp_dice"]),
        "speed": speed,
        "senses": _senses(access, creature_id),
        "skills": _skills(access, creature_id),
        "saving_throws": _saving_throws(access, creature_id),
        "passive_perception": creature_q.creature_passive_perception(access, creature_id),
        "attacks": _attacks(access, creature_id),
        "character_states": [],
    }
    if _int(row["ac_value"]):
        modifier["armor_class"] = row["ac_value"]
    defenses = _defenses(access, creature_id)
    if defenses is not None:
        modifier["defenses"] = defenses
    if not modifier["hit_dice"]:
        modifier.pop("hit_dice")
    # ability_scores is contract-required minProperties:1 WHEN present — a creature with no
    # ability rows (e.g. a header-only catalog entry) must omit the key, not emit {}.
    if not modifier["ability_scores"]:
        modifier.pop("ability_scores")

    assert "speed" in modifier and modifier["speed"], "companion speed is contract-required"
    assert "hit_points" in modifier, "companion hit_points is contract-required"
    return modifier


def derive_templated_stub(access, companion_index: int, creature_id: str, row) -> dict:
    """A minimal, contract-valid stub for a TEMPLATED creature (deferred to P2).

    Emits only the two contract-required fields from header facts — no formula
    evaluation. The scaling phase replaces this with the real formula-derived block.
    The concrete gold sheets in this slice do not exercise this path.
    """
    hp_max = _base_hp(row)
    speed = _speed(access, creature_id) or {"walk": 0}
    return {
        "companion_index": companion_index,
        "hit_points": {"max": hp_max, "current": hp_max, "temp": 0},
        "speed": speed,
    }


def derive_companion_modifier(access, companion_index: int, creature_id: str) -> dict | None:
    """Derive one companionModifier from a creature id. Returns None when the
    creature id does not resolve. Templated creatures are stubbed (P2 scaling)."""
    row = creature_q.creature_row(access, creature_id)
    if row is None:
        return None
    if is_templated(access, creature_id):
        return derive_templated_stub(access, companion_index, creature_id, row)
    return derive_concrete(access, companion_index, creature_id, row)


def derive_companion_modifiers(core: dict, access) -> list[dict]:
    """Derive every companionModifier for a CORE sheet's ``companions[]``. Each entry
    is resolved by ``db_creature_id``; unresolved / id-less entries are skipped."""
    companions = (core or {}).get("companions", []) or []
    if not isinstance(companions, list):
        return []
    result = []
    for idx, comp in enumerate(companions):
        if not isinstance(comp, dict):
            continue
        creature_id = comp.get("db_creature_id")
        if not creature_id:
            continue
        modifier = derive_companion_modifier(access, idx, creature_id)
        if modifier is not None:
            result.append(modifier)
    return result
