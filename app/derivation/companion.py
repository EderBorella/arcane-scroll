"""COMPANION derivation — concrete and templated creatures.

Pure functions that compute a ``companionModifier`` (companion-modifier:1 shape)
from a catalogued creature, read via ``access.validator.creature``. No
orchestrator, no non-overwritable protection, no session-state merge — those live
in ``companion_orchestrator``.

Two paths:

* CONCRETE creatures — a fixed statblock read verbatim from the catalog
  (:func:`derive_concrete`).
* TEMPLATED creatures — those carrying ``creature_formula`` rows whose block
  SCALES with the owner's cast level and spell/owner stats
  (:func:`derive_templated`). Owner context (cast level, owner class level,
  spell attack modifier, spell save DC, ability modifier, proficiency bonus) is
  resolved from the owning character's CORE + GRIMOIRE and passed in at runtime —
  it is never stored on the companion itself.

Each ``creature_formula`` names a ``target`` (ac / hp / attack_bonus /
attack_damage / save_dc / multiattack_count / pb) and evaluates to
``base + dice_average + Σ coefficient·variable`` (optionally rounded down).
``form_note`` gates a row to a chosen summoned form: a row with no note always
applies; a noted row applies only when its form matches the companion's chosen
form. Multiple applicable rows for one target sum.
"""
import collections
import math
import re

from access.validator import abilities as abilities_q
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


def _saving_throws(access, creature_id: str, pb) -> list:
    """Re-derive each save from the creature's own facts: ability modifier plus the
    creature's proficiency bonus for a PROFICIENT save. Save proficiencies are read
    from ``creature_save`` (presence = proficient); the bonus added is the creature's
    own ``pb`` (``creature.pb``), never an invented one. A save with no proficiency
    row is exactly its ability modifier. (This is a deliberate creature-shaped
    re-derivation, NOT the character-shaped MODIFIER saves helper.)"""
    scores = {r["ability_id"]: r["score"]
              for r in creature_q.creature_abilities(access, creature_id)
              if _int(r["score"])}
    proficient = {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}
    ordered = [a for a in _ABILITY_ORDER if a in scores]
    ordered += [a for a in scores if a not in _ABILITY_ORDER]
    result = []
    for aid in ordered:
        modifier = _ability_mod(scores[aid])
        if aid in proficient and _int(pb):
            modifier += pb
        result.append({"ability": aid, "modifier": modifier})
    return result


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


def derive_concrete(access, creature_id: str, row, companion_index: int | None = None) -> dict:
    """Derive a full stat block for one fixed-stat creature. Produces the shared
    owner-agnostic base (``statBlockBase`` shape); when ``companion_index`` is given
    it is added as the owner-linkage field (a ``companionModifier``), and when it is
    omitted the block is the bare owner-less base the standalone monster sheet uses.
    Asserts the contract-required ``hit_points`` and ``speed`` are present."""
    hp_max = _base_hp(row)
    speed = _speed(access, creature_id)
    if not speed:
        # A catalogued creature should always carry at least a walk speed; guard the
        # contract's minProperties:1 so a data gap can't produce an invalid block.
        speed = {"walk": 0}

    modifier: dict = {}
    if companion_index is not None:
        modifier["companion_index"] = companion_index
    modifier.update({
        "ability_scores": _ability_scores(access, creature_id),
        "hit_points": {"max": hp_max, "current": hp_max, "temp": 0},
        "hit_dice": _hit_dice(row["hp_dice"]),
        "speed": speed,
        "senses": _senses(access, creature_id),
        "skills": _skills(access, creature_id),
        "saving_throws": _saving_throws(access, creature_id, row["pb"]),
        "passive_perception": creature_q.creature_passive_perception(access, creature_id),
        "attacks": _attacks(access, creature_id),
        "character_states": [],
    })
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


# ── owner-context resolution (from the owning character's CORE + GRIMOIRE) ────
# These values feed the scaling formulas. They describe the OWNER, are derivable
# from CORE + GRIMOIRE, and are passed in at runtime — never stored on the
# companion. ``cast_level`` / ``form`` are the only per-companion runtime inputs
# and live on the CORE companions[] entry.


def _slug(value) -> str | None:
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
    """The class level that drives a subclass-granted companion (e.g. a beast
    companion scaling with its owner's class level). Falls back to the sole class
    level, then the total level."""
    if owner_kind == "subclass" and owner_id:
        for c in classes:
            if isinstance(c, dict) and _slug(c.get("subclass")) == owner_id and _int(c.get("level")):
                return c["level"]
    if len(classes) == 1 and isinstance(classes[0], dict) and _int(classes[0].get("level")):
        return classes[0]["level"]
    tl = identity.get("total_level")
    return tl if _int(tl) else None


def _spellcasting_ability(grimoire: dict, owner_id):
    """The spellcasting ability id that casts the granting spell. Prefer the source
    of a GRIMOIRE spell matching the owner (the summon spell); otherwise the first
    source that declares an ability."""
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


# ── formula evaluation (rule-grounded, reads creature_formula[_term] rows) ─────


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
    """A row with no form_note always applies; a noted row applies only when the
    companion's chosen form is one of the row's forms."""
    if form_note is None:
        return True
    if not form:
        return False
    return _slug(form) in _form_tokens(form_note)


def _eval_scalar(access, rows: list, ctx: dict, form):
    """Evaluate a scalar target (ac/hp/pb/save_dc/multiattack_count): sum every
    applicable row's ``base + dice_average + Σ coeff·variable`` (rounded down per
    row when the row says so). Returns None when no row applies."""
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
    # Scalar targets are integer-valued in practice; any residual fractional total
    # (a row without an explicit round_mode) is truncated toward floor by int().
    return int(total)


def _eval_damage(access, rows: list, ctx: dict, form):
    """Build a templated attack's damage string ``NdM + K`` where K is the row's
    flat term (base + Σ coeff·variable). Returns None when no row applies."""
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


def _templated_attacks(access, creature_id: str, by_target: dict,
                       multi_trait_ids: set, ctx: dict, form) -> list:
    """Templated attack entries. Each action trait's attack_bonus / attack_damage /
    save_dc are formula-scoped by ``trait_id``. The multi-attack action (the trait
    referenced by a multiattack_count formula) is represented by the ``multiattack``
    field, not as an attack. A save-forcing NON-action trait (an aura) still emits a
    name+save_dc entry so its scaled DC is not lost."""
    bonus_by_trait = _group_by_trait(by_target.get("attack_bonus", []))
    dmg_by_trait = _group_by_trait(by_target.get("attack_damage", []))
    save_by_trait = _group_by_trait(by_target.get("save_dc", []))

    result = []
    actions = creature_q.creature_actions(access, creature_id)
    action_ids = {t["id"] for t in actions}
    for trait in actions:
        tid = trait["id"]
        if tid in multi_trait_ids:
            continue
        entry = {"name": trait["name"]}
        bonus = _eval_scalar(access, bonus_by_trait.get(tid, []), ctx, form)
        if bonus is None and _int(trait["atk_bonus"]):
            bonus = trait["atk_bonus"]
        if _int(bonus):
            entry["attack_bonus"] = bonus
        damage = _eval_damage(access, dmg_by_trait.get(tid, []), ctx, form)
        if damage is None and isinstance(trait["dmg_dice"], str) and trait["dmg_dice"].strip():
            damage = trait["dmg_dice"].strip()
        if damage is not None:
            entry["damage"] = damage
        if trait["damage_type_id"]:
            entry["damage_type"] = trait["damage_type_id"]
        save_dc = _eval_scalar(access, save_by_trait.get(tid, []), ctx, form)
        if _int(save_dc):
            entry["save_dc"] = save_dc
        if len(entry) > 1:
            result.append(entry)

    for tid, rows in save_by_trait.items():
        if not tid or tid in action_ids:
            continue
        save_dc = _eval_scalar(access, rows, ctx, form)
        trait = creature_q.creature_trait_by_id(access, tid)
        if trait is not None and _int(save_dc):
            result.append({"name": trait["name"], "save_dc": save_dc})
    return result


def derive_templated(access, creature_id: str, row, ctx: dict, companion_index: int | None = None) -> dict:
    """Derive a full companionModifier for one TEMPLATED creature by evaluating its
    ``creature_formula`` rows against the resolved owner context. Non-scaled facts
    (ability scores, speed, senses, skills, saves, defences) are read straight from
    the catalog, exactly like a concrete creature."""
    formulas = creature_q.creature_formulas(access, creature_id)
    by_target: dict = collections.defaultdict(list)
    for f in formulas:
        by_target[f["target"]].append(f)
    form = ctx.get("form")

    multi_trait_ids = {f["trait_id"] for f in by_target.get("multiattack_count", []) if f["trait_id"]}

    ac = _eval_scalar(access, by_target.get("ac", []), ctx, form)
    hp = _eval_scalar(access, by_target.get("hp", []), ctx, form)
    pb = _eval_scalar(access, by_target.get("pb", []), ctx, form)
    multiattack = _eval_scalar(access, by_target.get("multiattack_count", []), ctx, form)

    # A target with no formula falls back to the stored header fact (mirrors concrete).
    if ac is None and _int(row["ac_value"]):
        ac = row["ac_value"]
    if hp is None and _int(row["hp_average"]):
        hp = row["hp_average"]
    hp = hp if _int(hp) else 0

    speed = _speed(access, creature_id) or {"walk": 0}
    attacks = _templated_attacks(access, creature_id, by_target, multi_trait_ids, ctx, form)

    modifier = {}
    if companion_index is not None:
        modifier["companion_index"] = companion_index
    modifier.update({
        "hit_points": {"max": hp, "current": hp, "temp": 0},
        "speed": speed,
        "character_states": [],
    })
    abilities = _ability_scores(access, creature_id)
    if abilities:
        modifier["ability_scores"] = abilities
        modifier["saving_throws"] = _saving_throws(access, creature_id, row["pb"])
    senses = _senses(access, creature_id)
    if senses:
        modifier["senses"] = senses
    skills = _skills(access, creature_id)
    if skills:
        modifier["skills"] = skills
    pp = creature_q.creature_passive_perception(access, creature_id)
    if _int(pp):
        modifier["passive_perception"] = pp
    if _int(ac):
        modifier["armor_class"] = ac
    if _int(pb):
        modifier["proficiency_bonus"] = pb
    if _int(multiattack):
        modifier["multiattack"] = multiattack
    if attacks:
        modifier["attacks"] = attacks
    defenses = _defenses(access, creature_id)
    if defenses is not None:
        modifier["defenses"] = defenses

    assert modifier["speed"], "companion speed is contract-required"
    return modifier


def derive_companion_modifier(access, companion_index: int, creature_id: str,
                              comp_entry: dict | None = None,
                              core: dict | None = None,
                              grimoire: dict | None = None) -> dict | None:
    """Derive one companionModifier from a creature id. Returns None when the
    creature id does not resolve. Templated creatures are formula-scaled against the
    owner context resolved from ``core`` + ``grimoire`` + the companion entry."""
    row = creature_q.creature_row(access, creature_id)
    if row is None:
        return None
    if is_templated(access, creature_id):
        ctx = _owner_context(core, grimoire, access, creature_id, comp_entry or {})
        return derive_templated(access, creature_id, row, ctx, companion_index)
    return derive_concrete(access, creature_id, row, companion_index)


def derive_companion_modifiers(core: dict, access, grimoire: dict | None = None) -> list[dict]:
    """Derive every companionModifier for a CORE sheet's ``companions[]``. Each entry
    is resolved by ``db_creature_id``; unresolved / id-less entries are skipped.
    ``grimoire`` supplies the owner's spell attack/save context for templated
    creatures (ignored for concrete creatures)."""
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
        modifier = derive_companion_modifier(access, idx, creature_id, comp, core, grimoire)
        if modifier is not None:
            result.append(modifier)
    return result
