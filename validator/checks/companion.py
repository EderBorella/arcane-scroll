"""COMPANION domain (companion-modifier:1 shape): validates a companion sheet
against DB facts + the CORE companions[] identities.

Every value is INDEPENDENTLY re-derived from the creature catalog (and, for
templated creatures, from the resolved owner context) and compared to the sheet.
The check NEVER reads the deriver's output — it reads the creature rows and
evaluates the rules itself.

* CONCRETE creatures: every fixed-stat field (AC, HP, hit dice, speed, senses,
  abilities, saves, skills, passive perception, attacks, defences) is re-derived
  verbatim from the catalog.
* TEMPLATED creatures (those carrying creature_formula rows): the SCALED targets
  (ac, hp, pb, multiattack, attack bonus/damage/save DC) are re-derived by
  evaluating the ``creature_formula`` rows against an owner context resolved
  independently from CORE + GRIMOIRE; the non-scaled facts (abilities, speed,
  senses, skills, saves, defences) reuse the concrete checks unchanged.

NOT in ALL_CHECKS — companion-modifier:1-specific, run via POST /validate-companion.
"""
import collections
import math
import re

from access.validator import abilities as abilities_q
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
    """Expected save modifier per ability, INDEPENDENTLY re-derived from the catalog:
    the ability modifier, plus the creature's own proficiency bonus (``creature.pb``)
    for a save the creature is proficient in (a ``creature_save`` marker row). Reads
    the DB facts directly — never the deriver's output."""
    scores = _expected_abilities(access, creature_id)
    if not scores:
        return {}
    proficient = {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}
    pb = None
    if proficient:
        row = creature_q.creature_row(access, creature_id)
        pb = row["pb"] if row is not None else None
    out = {}
    for aid, score in scores.items():
        modifier = _ability_mod(score)
        if aid in proficient and _int(pb):
            modifier += pb
        out[aid] = modifier
    return out


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


# ── templated scaling: independent owner-context resolution + formula eval ────
# Re-derived from the reference DB + CORE + GRIMOIRE. This NEVER reads the
# deriver's output; it evaluates the creature_formula rules from scratch, so a
# wrong scaled value on the sheet is flagged.


def _slug(value):
    if not isinstance(value, str):
        return None
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or None


def _final_score(access, abilities: dict, ability_id):
    """The CORE final score for a full DB ability id. CORE keys abilities by their
    short code (the ability's abbrev) while the DB/GRIMOIRE use the full id; bridge
    via the ability table's abbrev (ruleset-as-data, not a hardcoded map)."""
    if not ability_id:
        return None
    entry = abilities.get(ability_id)
    if not isinstance(entry, dict):
        norm = {abilities_q.ability_id_for_short_key(access, k): v for k, v in abilities.items()}
        entry = norm.get(ability_id)
    if not isinstance(entry, dict):
        return None
    final = entry.get("final")
    return final if _int(final) else None


def _owner_class_level(classes: list, identity: dict, owner_kind, owner_id):
    if owner_kind == "subclass" and owner_id:
        for c in classes:
            if isinstance(c, dict) and _slug(c.get("subclass")) == owner_id and _int(c.get("level")):
                return c["level"]
    if len(classes) == 1 and isinstance(classes[0], dict) and _int(classes[0].get("level")):
        return classes[0]["level"]
    tl = identity.get("total_level")
    return tl if _int(tl) else None


def _spellcasting_ability(grimoire: dict, owner_id):
    sources = grimoire.get("sources") or {}
    for sp in grimoire.get("spells") or []:
        if isinstance(sp, dict) and sp.get("name") == owner_id:
            src = sources.get(sp.get("source"))
            if isinstance(src, dict) and src.get("ability"):
                return src["ability"]
    for src in sources.values():
        if isinstance(src, dict) and src.get("ability"):
            return src["ability"]
    return None


def _owner_context(core: dict, grimoire: dict, access, creature_id: str, comp_entry: dict) -> dict:
    core = core or {}
    grimoire = grimoire or {}
    identity = core.get("identity") or {}
    classes = identity.get("classes") or []
    pb = core.get("proficiency_bonus")
    pb = pb if _int(pb) else None
    abilities = core.get("abilities") or {}

    wis = _final_score(access, abilities, "wisdom")
    wis_mod = _ability_mod(wis) if _int(wis) else 0

    grants = creature_q.companion_grants_for_creature(access, creature_id)
    owner_kind = grants[0]["owner_kind"] if grants else None
    owner_id = grants[0]["owner_id"] if grants else None

    ability = _spellcasting_ability(grimoire, owner_id)
    ab_score = _final_score(access, abilities, ability) if ability else None
    ab_mod = _ability_mod(ab_score) if _int(ab_score) else None
    spell_attack = pb + ab_mod if pb is not None and ab_mod is not None else None
    spell_save = 8 + pb + ab_mod if pb is not None and ab_mod is not None else None

    return {
        "cast_level": comp_entry.get("cast_level") if isinstance(comp_entry, dict) else None,
        "form": comp_entry.get("form") if isinstance(comp_entry, dict) else None,
        "owner_class_level": _owner_class_level(classes, identity, owner_kind, owner_id),
        "spell_attack_modifier": spell_attack,
        "spell_save_dc": spell_save,
        "owner_wisdom_modifier": wis_mod,
        "owner_proficiency_bonus": pb,
    }


def _dice_average(die_count, die_faces) -> float:
    if _int(die_count) and _int(die_faces):
        return die_count * (die_faces + 1) / 2
    return 0.0


def _variable_base(variable: str, above_level, ctx: dict):
    cast = ctx.get("cast_level")
    if variable == "spell_level":
        return cast
    if variable == "spell_level_above_base":
        return max(0, cast - (above_level or 0)) if _int(cast) else 0
    if variable == "owner_class_level":
        return ctx.get("owner_class_level")
    if variable == "spell_attack_modifier":
        return ctx.get("spell_attack_modifier")
    if variable == "spell_save_dc":
        return ctx.get("spell_save_dc")
    if variable == "owner_wisdom_modifier":
        return ctx.get("owner_wisdom_modifier")
    if variable == "owner_proficiency_bonus":
        return ctx.get("owner_proficiency_bonus")
    return 0


def _term_value(term, ctx: dict) -> float:
    base = _variable_base(term["variable"], term["above_level"], ctx)
    return term["coefficient"] * (base if base is not None else 0)


def _form_tokens(form_note: str) -> set:
    s = form_note.strip()
    if s.lower().endswith(" only"):
        s = s[: -len(" only")]
    return {_slug(part) for part in s.split(" and ") if part.strip()}


def _form_applies(form_note, form) -> bool:
    if form_note is None:
        return True
    if not form:
        return False
    return _slug(form) in _form_tokens(form_note)


def _eval_scalar(access, rows: list, ctx: dict, form):
    applicable = [r for r in rows if _form_applies(r["form_note"], form)]
    if not applicable:
        return None
    total = 0.0
    for r in applicable:
        val = (r["base"] or 0) + _dice_average(r["die_count"], r["die_faces"])
        for t in creature_q.creature_formula_terms(access, r["id"]):
            val += _term_value(t, ctx)
        if r["round_mode"] == "down":
            val = math.floor(val)
        total += val
    return int(total)


def _eval_damage(access, rows: list, ctx: dict, form):
    applicable = [r for r in rows if _form_applies(r["form_note"], form)]
    if not applicable:
        return None
    r = applicable[0]
    flat = r["base"] or 0
    for t in creature_q.creature_formula_terms(access, r["id"]):
        flat += _term_value(t, ctx)
    if r["round_mode"] == "down":
        flat = math.floor(flat)
    flat = int(flat)
    dice = f"{r['die_count']}d{r['die_faces']}" if _int(r["die_count"]) and _int(r["die_faces"]) else None
    if dice and flat:
        return f"{dice} {'+' if flat >= 0 else '-'} {abs(flat)}"
    if dice:
        return dice
    return str(flat)


def _group_by_trait(rows: list) -> dict:
    grouped: dict = collections.defaultdict(list)
    for r in rows:
        grouped[r["trait_id"]].append(r)
    return grouped


def _formulas_by_target(access, creature_id: str) -> dict:
    by_target: dict = collections.defaultdict(list)
    for f in creature_q.creature_formulas(access, creature_id):
        by_target[f["target"]].append(f)
    return by_target


def _check_scaled_hp(cm, expected, v, idx) -> None:
    if expected is None:
        return
    hp = cm.get("hit_points")
    actual = hp.get("max") if isinstance(hp, dict) else None
    if not _int(actual):
        v.append(Violation(DOMAIN, "companion-hp-missing", "incomplete",
                           f"companion {idx}: hit_points.max omitted but formula scales to {expected}",
                           f"companion_modifiers.{idx}.hit_points.max"))
        return
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-hp-mismatch", "illegal",
                           f"companion {idx}: hit_points.max {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.hit_points.max"))


def _check_scaled_ac(cm, expected, v, idx) -> None:
    if expected is None:
        return
    actual = cm.get("armor_class")
    if not _int(actual):
        v.append(Violation(DOMAIN, "companion-ac-missing", "incomplete",
                           f"companion {idx}: armor_class omitted but formula scales to {expected}",
                           f"companion_modifiers.{idx}.armor_class"))
        return
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-ac-mismatch", "illegal",
                           f"companion {idx}: armor_class {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.armor_class"))


def _check_scaled_pb(cm, expected, v, idx) -> None:
    if expected is None:
        return
    actual = cm.get("proficiency_bonus")
    if not _int(actual):
        v.append(Violation(DOMAIN, "companion-pb-missing", "incomplete",
                           f"companion {idx}: proficiency_bonus omitted but formula scales to {expected}",
                           f"companion_modifiers.{idx}.proficiency_bonus"))
        return
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-pb-mismatch", "illegal",
                           f"companion {idx}: proficiency_bonus {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.proficiency_bonus"))


def _check_multiattack(cm, expected, v, idx) -> None:
    if expected is None:
        return
    actual = cm.get("multiattack")
    if not _int(actual):
        v.append(Violation(DOMAIN, "companion-multiattack-missing", "incomplete",
                           f"companion {idx}: multiattack omitted but formula scales to {expected}",
                           f"companion_modifiers.{idx}.multiattack"))
        return
    if actual != expected:
        v.append(Violation(DOMAIN, "companion-multiattack-mismatch", "illegal",
                           f"companion {idx}: multiattack {actual} != expected {expected}",
                           f"companion_modifiers.{idx}.multiattack"))


def _check_scaled_attacks(access, cm, creature_id, by_target, ctx, form, v, idx) -> None:
    """Re-derive each templated action/ability's scaled bonus / damage / save DC from
    the formula rows and owner context, matched to the sheet by name. Covers both
    attack actions AND save-forcing NON-action traits (auras), mirroring the
    deriver so a save DC emitted on an aura is checked, not silently accepted."""
    bonus_by_trait = _group_by_trait(by_target.get("attack_bonus", []))
    dmg_by_trait = _group_by_trait(by_target.get("attack_damage", []))
    save_by_trait = _group_by_trait(by_target.get("save_dc", []))
    multi_trait_ids = {f["trait_id"] for f in by_target.get("multiattack_count", []) if f["trait_id"]}

    expected = {}
    actions = creature_q.creature_actions(access, creature_id)
    action_ids = {t["id"] for t in actions}
    for trait in actions:
        tid = trait["id"]
        if tid in multi_trait_ids:
            continue
        exp_bonus = _eval_scalar(access, bonus_by_trait.get(tid, []), ctx, form)
        if exp_bonus is None and _int(trait["atk_bonus"]):
            exp_bonus = trait["atk_bonus"]
        exp_damage = _eval_damage(access, dmg_by_trait.get(tid, []), ctx, form)
        if exp_damage is None and isinstance(trait["dmg_dice"], str) and trait["dmg_dice"].strip():
            exp_damage = trait["dmg_dice"].strip()
        exp_save = _eval_scalar(access, save_by_trait.get(tid, []), ctx, form)
        if exp_bonus is not None or exp_damage is not None or _int(exp_save):
            expected[trait["name"]] = (exp_bonus, exp_damage, exp_save)

    # Save-forcing NON-action traits (auras) also carry a scaled save DC.
    for tid, rows in save_by_trait.items():
        if not tid or tid in action_ids:
            continue
        exp_save = _eval_scalar(access, rows, ctx, form)
        trait = creature_q.creature_trait_by_id(access, tid)
        if trait is not None and _int(exp_save):
            expected[trait["name"]] = (None, None, exp_save)

    actual_by_name = {}
    attacks = cm.get("attacks")
    if isinstance(attacks, list):
        for atk in attacks:
            if isinstance(atk, dict) and atk.get("name") is not None:
                actual_by_name.setdefault(atk["name"], atk)

    for name, (exp_bonus, exp_damage, exp_save) in expected.items():
        atk = actual_by_name.get(name)
        if atk is None:
            v.append(Violation(DOMAIN, "companion-attack-missing", "incomplete",
                               f"companion {idx}: scaled attack {name!r} not on the sheet",
                               f"companion_modifiers.{idx}.attacks"))
            continue
        if exp_bonus is not None:
            if not _int(atk.get("attack_bonus")):
                v.append(Violation(DOMAIN, "companion-attack-bonus-missing", "incomplete",
                                   f"companion {idx}: attack {name!r} attack_bonus omitted but "
                                   f"scales to {exp_bonus}", f"companion_modifiers.{idx}.attacks"))
            elif atk["attack_bonus"] != exp_bonus:
                v.append(Violation(DOMAIN, "companion-attack-bonus-mismatch", "illegal",
                                   f"companion {idx}: attack {name!r} bonus {atk['attack_bonus']} "
                                   f"!= expected {exp_bonus}", f"companion_modifiers.{idx}.attacks"))
        if exp_damage is not None:
            if atk.get("damage") is None:
                v.append(Violation(DOMAIN, "companion-attack-damage-missing", "incomplete",
                                   f"companion {idx}: attack {name!r} damage omitted but "
                                   f"scales to {exp_damage!r}", f"companion_modifiers.{idx}.attacks"))
            elif atk["damage"] != exp_damage:
                v.append(Violation(DOMAIN, "companion-attack-damage-mismatch", "illegal",
                                   f"companion {idx}: attack {name!r} damage {atk.get('damage')!r} "
                                   f"!= expected {exp_damage!r}", f"companion_modifiers.{idx}.attacks"))
        if _int(exp_save):
            if not _int(atk.get("save_dc")):
                v.append(Violation(DOMAIN, "companion-attack-save-dc-missing", "incomplete",
                                   f"companion {idx}: attack {name!r} save_dc omitted but "
                                   f"scales to {exp_save}", f"companion_modifiers.{idx}.attacks"))
            elif atk["save_dc"] != exp_save:
                v.append(Violation(DOMAIN, "companion-attack-save-dc-mismatch", "illegal",
                                   f"companion {idx}: attack {name!r} save_dc {atk.get('save_dc')} "
                                   f"!= expected {exp_save}", f"companion_modifiers.{idx}.attacks"))


def _check_templated(access, core, grimoire, cm, creature_id, row, core_entry, v, idx) -> None:
    """Independent re-derivation of a templated companion. Scaled targets come from
    the creature_formula rules + owner context; non-scaled facts reuse the concrete
    field checks unchanged."""
    ctx = _owner_context(core, grimoire, access, creature_id, core_entry)
    form = ctx.get("form")
    by_target = _formulas_by_target(access, creature_id)

    # Non-scaled catalog facts still apply verbatim.
    _check_speed(access, cm, creature_id, v, idx)
    _check_senses(access, cm, creature_id, v, idx)
    _check_abilities(access, cm, creature_id, v, idx)
    _check_saves(access, cm, creature_id, v, idx)
    _check_skills(access, cm, creature_id, v, idx)
    _check_passive(access, cm, creature_id, v, idx)
    _check_defenses(access, cm, creature_id, v, idx)

    # Scaled targets: re-derived from the formula rules + owner context.
    exp_hp = _eval_scalar(access, by_target.get("hp", []), ctx, form)
    if exp_hp is None and _int(row["hp_average"]):
        exp_hp = row["hp_average"]
    exp_ac = _eval_scalar(access, by_target.get("ac", []), ctx, form)
    if exp_ac is None and _int(row["ac_value"]):
        exp_ac = row["ac_value"]
    _check_scaled_hp(cm, exp_hp, v, idx)
    _check_scaled_ac(cm, exp_ac, v, idx)
    _check_scaled_pb(cm, _eval_scalar(access, by_target.get("pb", []), ctx, form), v, idx)
    _check_multiattack(cm, _eval_scalar(access, by_target.get("multiattack_count", []), ctx, form), v, idx)
    _check_scaled_attacks(access, cm, creature_id, by_target, ctx, form, v, idx)


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    companion = sheet.get("companion")
    if not isinstance(companion, dict):
        return v
    core = sheet.get("core", {}) or {}
    grimoire = sheet.get("grimoire", {}) or {}
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
            # Templated creatures are formula-scaled: re-derive the scaled targets
            # from the creature_formula rules + owner context, and reuse the concrete
            # checks for the non-scaled catalog facts.
            _check_templated(access, core, grimoire, cm, creature_id, row, core_entry, v, idx)
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
