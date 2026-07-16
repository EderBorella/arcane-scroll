"""COMPANION domain (companion-modifier:1 shape): validates a companion sheet
against DB facts + the CORE companions[] identities.

Concrete-creature slice: every fixed-stat field (AC, HP, hit dice, speed, senses,
abilities, saves, skills, passive perception, attacks, defences) is INDEPENDENTLY
re-derived from the creature catalog and compared to the sheet. The check NEVER
reads the deriver's output — it reads the creature rows itself.

Templated creatures (those carrying creature_formula rows) are formula-scaled by
the owner's spell level; their statblock re-derivation is deferred to the scaling
phase (P2). Here they are only shape-checked — index range, resolvable creature,
and state validity — the numeric re-derivation is skipped.

NOT in ALL_CHECKS — companion-modifier:1-specific, run via POST /validate-companion.
"""
import re

from access.validator import creature as creature_q
from access.validator.state_compatibility import blocked_states
from validator.report import Violation

DOMAIN = "companion"

# Canonical ability-id order (mirrors the deriver's stable emission order).
_ABILITY_ORDER = (
    "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma",
)


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ability_mod(score: int) -> int:
    return (score - 10) // 2


def _is_templated(access, creature_id: str) -> bool:
    return bool(creature_q.creature_formulas(access, creature_id))


# ── expected-value re-derivation (independent of the deriver) ────────────────


def _expected_speed(access, creature_id: str) -> dict:
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
    if not result:
        # Mirror the deriver's contract floor (speed is minProperties:1) so a
        # speed-less creature round-trips clean instead of a false mismatch.
        result = {"walk": 0}
    return result


def _expected_senses(access, creature_id: str) -> dict:
    return {r["sense_id"]: r["range_ft"]
            for r in creature_q.creature_senses(access, creature_id)
            if _int(r["range_ft"])}


def _expected_skills(access, creature_id: str) -> dict:
    return {r["skill_id"]: r["bonus"]
            for r in creature_q.creature_skills(access, creature_id)
            if _int(r["bonus"])}


def _expected_abilities(access, creature_id: str) -> dict:
    return {r["ability_id"]: r["score"]
            for r in creature_q.creature_abilities(access, creature_id)
            if _int(r["score"])}


def _expected_saves(access, creature_id: str) -> dict:
    scores = _expected_abilities(access, creature_id)
    return {aid: _ability_mod(score) for aid, score in scores.items()}


def _expected_attacks(access, creature_id: str) -> dict:
    """Expected attacks keyed by name → (attack_bonus, damage, damage_type)."""
    out = {}
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
        out[row["name"]] = (atk_bonus, damage, row["damage_type_id"])
    return out


# ── per-companion checks ─────────────────────────────────────────────────────


def _expected_hit_dice(row) -> dict:
    """Expected hit-dice max keyed by die id ('dM' → count), re-derived from the
    creature's HP-dice expression's leading NdM term."""
    hp_dice = row["hp_dice"]
    if not isinstance(hp_dice, str):
        return {}
    m = re.search(r"(\d+)\s*d\s*(\d+)", hp_dice)
    if not m:
        return {}
    return {f"d{int(m.group(2))}": int(m.group(1))}


def _check_hp(cm: dict, row, v: list[Violation], idx) -> None:
    hp = cm.get("hit_points")
    if not isinstance(hp, dict):
        return
    actual = hp.get("max")
    expected = row["hp_average"] if _int(row["hp_average"]) else 0
    if _int(actual) and actual != expected:
        v.append(Violation(DOMAIN, "companion-hp-mismatch", "illegal",
                           f"companion {idx}: hit_points.max {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.hit_points.max"))


def _check_hit_dice(cm: dict, row, v: list[Violation], idx) -> None:
    """Independently re-derive the hit-dice max (count/faces) from the creature's
    hp_dice and flag a mismatch or a missing die. ``remaining`` is live session
    state (non-overwritable) and is deliberately NOT validated."""
    expected = _expected_hit_dice(row)
    if not expected:
        return
    hd = cm.get("hit_dice")
    if not isinstance(hd, dict):
        v.append(Violation(DOMAIN, "companion-hit-dice-missing", "incomplete",
                           f"companion {idx}: hit_dice omitted but creature has hp_dice",
                           f"companion_modifiers.{idx}.hit_dice"))
        return
    for die, exp_max in expected.items():
        entry = hd.get(die)
        if not isinstance(entry, dict) or not _int(entry.get("max")):
            v.append(Violation(DOMAIN, "companion-hit-dice-missing", "incomplete",
                               f"companion {idx}: hit_dice die {die!r} (max {exp_max}) missing",
                               f"companion_modifiers.{idx}.hit_dice"))
        elif entry["max"] != exp_max:
            v.append(Violation(DOMAIN, "companion-hit-dice-mismatch", "illegal",
                               f"companion {idx}: hit_dice {die} max {entry['max']} "
                               f"!= expected {exp_max}",
                               f"companion_modifiers.{idx}.hit_dice"))


def _check_ac(cm: dict, row, v: list[Violation], idx) -> None:
    expected = row["ac_value"]
    actual = cm.get("armor_class")
    if actual is None or not _int(actual):
        if _int(expected):
            v.append(Violation(DOMAIN, "companion-ac-missing", "incomplete",
                               f"companion {idx}: armor_class omitted but creature has AC "
                               f"{expected}", f"companion_modifiers.{idx}.armor_class"))
        return
    if _int(expected) and actual != expected:
        v.append(Violation(DOMAIN, "companion-ac-mismatch", "illegal",
                           f"companion {idx}: armor_class {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.armor_class"))


def _check_speed(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    actual = cm.get("speed")
    if not isinstance(actual, dict):
        return
    expected = _expected_speed(access, creature_id)
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-speed-mismatch", "illegal",
                           f"companion {idx}: speed {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.speed"))


def _check_senses(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    actual = cm.get("senses")
    if actual is None:
        actual = {}
    if not isinstance(actual, dict):
        return
    expected = _expected_senses(access, creature_id)
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-senses-mismatch", "illegal",
                           f"companion {idx}: senses {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.senses"))


def _check_abilities(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    expected = _expected_abilities(access, creature_id)
    actual = cm.get("ability_scores")
    if not isinstance(actual, dict):
        if expected:
            v.append(Violation(DOMAIN, "companion-abilities-missing", "incomplete",
                               f"companion {idx}: ability_scores omitted but creature has "
                               f"ability rows", f"companion_modifiers.{idx}.ability_scores"))
        return
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-abilities-mismatch", "illegal",
                           f"companion {idx}: ability_scores {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.ability_scores"))


def _check_saves(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    expected = _expected_saves(access, creature_id)
    if not expected:
        return
    saves = cm.get("saving_throws")
    if not isinstance(saves, list):
        v.append(Violation(DOMAIN, "companion-save-missing", "incomplete",
                           f"companion {idx}: saving_throws omitted but creature has abilities",
                           f"companion_modifiers.{idx}.saving_throws"))
        return
    actual = {}
    for s in saves:
        if isinstance(s, dict) and s.get("ability") is not None and _int(s.get("modifier")):
            actual[s["ability"]] = s["modifier"]
    for aid, exp_mod in expected.items():
        if aid not in actual:
            v.append(Violation(DOMAIN, "companion-save-missing", "incomplete",
                               f"companion {idx}: save {aid} (expected {exp_mod}) missing",
                               f"companion_modifiers.{idx}.saving_throws"))
        elif actual[aid] != exp_mod:
            v.append(Violation(DOMAIN, "companion-save-mismatch", "illegal",
                               f"companion {idx}: save {aid} {actual[aid]} != expected {exp_mod}",
                               f"companion_modifiers.{idx}.saving_throws"))


def _check_skills(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    expected = _expected_skills(access, creature_id)
    skills = cm.get("skills")
    if not isinstance(skills, list):
        if expected:
            v.append(Violation(DOMAIN, "companion-skills-missing", "incomplete",
                               f"companion {idx}: skills omitted but creature has catalogued "
                               f"skills", f"companion_modifiers.{idx}.skills"))
        return
    actual = {}
    for s in skills:
        if isinstance(s, dict) and s.get("name") is not None and _int(s.get("bonus")):
            actual[s["name"]] = s["bonus"]
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-skills-mismatch", "illegal",
                           f"companion {idx}: skills {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.skills"))


def _check_passive(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    expected = creature_q.creature_passive_perception(access, creature_id)
    actual = cm.get("passive_perception")
    if actual is None or not _int(actual):
        if _int(expected):
            v.append(Violation(DOMAIN, "companion-passive-missing", "incomplete",
                               f"companion {idx}: passive_perception omitted but creature has "
                               f"{expected}", f"companion_modifiers.{idx}.passive_perception"))
        return
    if _int(expected) and actual != expected:
        v.append(Violation(DOMAIN, "companion-passive-mismatch", "illegal",
                           f"companion {idx}: passive_perception {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.passive_perception"))


def _check_attacks(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    attacks = cm.get("attacks")
    if not isinstance(attacks, list):
        return
    expected = _expected_attacks(access, creature_id)
    actual_names = set()
    for atk in attacks:
        if not isinstance(atk, dict):
            continue
        name = atk.get("name")
        if name is None:
            continue
        actual_names.add(name)
        if name not in expected:
            continue
        exp_bonus, exp_damage, exp_type = expected[name]
        # NIT (P2): attack_bonus may also be a string for a templated attack whose bonus is
        # formula-scaled; concrete creatures always store an int, so int-compare here.
        if _int(atk.get("attack_bonus")) and atk["attack_bonus"] != exp_bonus:
            v.append(Violation(DOMAIN, "companion-attack-bonus-mismatch", "illegal",
                               f"companion {idx}: attack {name!r} bonus {atk['attack_bonus']} "
                               f"!= expected {exp_bonus}",
                               f"companion_modifiers.{idx}.attacks"))
        if atk.get("damage") is not None and atk.get("damage") != exp_damage:
            v.append(Violation(DOMAIN, "companion-attack-damage-mismatch", "illegal",
                               f"companion {idx}: attack {name!r} damage {atk.get('damage')!r} "
                               f"!= expected {exp_damage!r}",
                               f"companion_modifiers.{idx}.attacks"))
        if atk.get("damage_type") is not None and atk.get("damage_type") != exp_type:
            v.append(Violation(DOMAIN, "companion-attack-damage-type-mismatch", "illegal",
                               f"companion {idx}: attack {name!r} damage_type "
                               f"{atk.get('damage_type')!r} != expected {exp_type!r}",
                               f"companion_modifiers.{idx}.attacks"))
    # Every catalogued attack must be present (a missing attack is incomplete).
    for name in expected:
        if name not in actual_names:
            v.append(Violation(DOMAIN, "companion-attack-missing", "incomplete",
                               f"companion {idx}: catalogued attack {name!r} not on the sheet",
                               f"companion_modifiers.{idx}.attacks"))


def _check_defenses(access, cm: dict, creature_id: str, v: list[Violation], idx) -> None:
    """The sheet's defences must include every catalogued defence (subset check)."""
    d = creature_q.creature_defenses(access, creature_id)
    exp_res = {r["damage_type_id"] for r in d["resistance"] if r["damage_type_id"]}
    exp_imm_dmg = {r["damage_type_id"] for r in d["immunity_damage"] if r["damage_type_id"]}
    exp_imm_cond = {r["condition_id"] for r in d["immunity_condition"] if r["condition_id"]}
    exp_vuln = {r["damage_type_id"] for r in d["vulnerability"] if r["damage_type_id"]}
    if not (exp_res or exp_imm_dmg or exp_imm_cond or exp_vuln):
        return

    defenses = cm.get("defenses") or {}
    if not isinstance(defenses, dict):
        defenses = {}
    got_res = set(defenses.get("resistance", []) or [])
    immunity = defenses.get("immunity", {}) or {}
    got_imm_dmg = set(immunity.get("damage", []) or []) if isinstance(immunity, dict) else set()
    got_imm_cond = set(immunity.get("condition", []) or []) if isinstance(immunity, dict) else set()
    got_vuln = set(defenses.get("vulnerability", []) or [])

    for label, missing in (
        ("resistance", exp_res - got_res),
        ("immunity.damage", exp_imm_dmg - got_imm_dmg),
        ("immunity.condition", exp_imm_cond - got_imm_cond),
        ("vulnerability", exp_vuln - got_vuln),
    ):
        for m in sorted(missing):
            v.append(Violation(DOMAIN, "companion-defense-subset-violation", "illegal",
                               f"companion {idx}: missing catalogued {label} {m!r}",
                               f"companion_modifiers.{idx}.defenses.{label}"))


def _check_states(access, cm: dict, v: list[Violation], idx) -> None:
    """A companion's character_states[] must be mutually compatible (same
    state_compatibility rule as the MODIFIER state check)."""
    states = cm.get("character_states")
    if not isinstance(states, list) or len(states) < 2:
        return
    active = set()
    for s in states:
        if isinstance(s, dict) and s.get("state"):
            active.add(s["state"])
    for sid in active:
        for c in blocked_states(access.db, sid) & active:
            v.append(Violation(DOMAIN, "companion-state-incompatible", "illegal",
                               f"companion {idx}: state {sid!r} is incompatible with {c!r}",
                               f"companion_modifiers.{idx}.character_states"))


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    companion = sheet.get("companion")
    if not isinstance(companion, dict):
        return v
    core = sheet.get("core", {}) or {}
    companions = core.get("companions", []) or []
    if not isinstance(companions, list):
        companions = []

    modifiers = companion.get("companion_modifiers")
    if not isinstance(modifiers, list):
        return v

    for cm in modifiers:
        if not isinstance(cm, dict):
            continue
        idx = cm.get("companion_index")
        if not _int(idx):
            v.append(Violation(DOMAIN, "companion-index-invalid", "illegal",
                               f"companion_index {idx!r} is not an integer",
                               "companion_modifiers"))
            continue
        if idx < 0 or idx >= len(companions):
            v.append(Violation(DOMAIN, "companion-index-out-of-range", "illegal",
                               f"companion_index {idx} out of range of CORE.companions[] "
                               f"(len {len(companions)})",
                               f"companion_modifiers.{idx}.companion_index"))
            # state validity can still be checked without a resolvable creature
            _check_states(access, cm, v, idx)
            continue

        core_entry = companions[idx]
        creature_id = core_entry.get("db_creature_id") if isinstance(core_entry, dict) else None
        if not creature_id:
            v.append(Violation(DOMAIN, "companion-creature-missing-id", "illegal",
                               f"companion {idx}: CORE.companions[{idx}] has no db_creature_id",
                               f"companion_modifiers.{idx}.companion_index"))
            _check_states(access, cm, v, idx)
            continue

        row = creature_q.creature_row(access, creature_id)
        if row is None:
            v.append(Violation(DOMAIN, "companion-creature-unknown", "illegal",
                               f"companion {idx}: db_creature_id {creature_id!r} does not resolve",
                               f"companion_modifiers.{idx}.companion_index"))
            _check_states(access, cm, v, idx)
            continue

        # State validity is shape-level and always checked.
        _check_states(access, cm, v, idx)

        if _is_templated(access, creature_id):
            # Templated creatures are formula-scaled — the numeric re-derivation is
            # deferred to the scaling phase (P2). Only the shape/index/creature/state
            # checks above apply in this slice.
            continue

        _check_hp(cm, row, v, idx)
        _check_hit_dice(cm, row, v, idx)
        _check_ac(cm, row, v, idx)
        _check_speed(access, cm, creature_id, v, idx)
        _check_senses(access, cm, creature_id, v, idx)
        _check_abilities(access, cm, creature_id, v, idx)
        _check_saves(access, cm, creature_id, v, idx)
        _check_skills(access, cm, creature_id, v, idx)
        _check_passive(access, cm, creature_id, v, idx)
        _check_attacks(access, cm, creature_id, v, idx)
        _check_defenses(access, cm, creature_id, v, idx)

    return v
