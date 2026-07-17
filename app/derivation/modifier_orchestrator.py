"""C-M2: MODIFIER orchestrator. Drives C-M1 derivation functions to produce a modifier-sheet:1
dict. Three modes: (a) fill from scratch, (b) fill gaps + protect non-overwritable fields,
(c) skip derivation. Applies source-name dedup on bonuses (highest-wins same-spell rule)."""
from collections import defaultdict

from app.derivation.grimoire import hash_core
from app.derivation.modifier import (
    ActiveEffects, resolve_active_effects,
    derive_abilities, derive_ac, derive_speed, derive_defenses, derive_size,
    derive_saving_throws, derive_skills, derive_passive_scores,
    derive_initiative, derive_hp_effects, derive_form_temp_pool, derive_resource_state,
    derive_attacks, derive_senses, derive_features, derive_feats,
)


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


# ── non-overwritable field paths (from modifier-sheet.schema.json $comment) ──

NON_OVERWRITABLE = frozenset({
    "xp",
    "treasure.*",
    "hit_points.current", "hit_points.temp",
    # A live variable-drain magnitude and a self-transform's temporary form-HP pool are live-play
    # amounts, not static-derivable facts (T112 / T108), so a gap-fill re-derive must preserve a
    # supplied value rather than clobber it with the static build's 0/absent derivation (T117).
    "hit_points.max_reduction", "hit_points.form_temp_pool",
    "death_saves.*",
    "hit_dice.*.remaining",
    "spell_slots.*.remaining", "pact_slots.*.remaining",
    "resource_state.*.remaining",
    "features.*.uses.remaining", "feats.*.uses.remaining",
    "item_states.*.attuned", "item_states.*.consumed",
    "item_states.*.charges.remaining", "item_states.*.cumulative_seconds_used",
    "prepared_spells", "character_states",
})


def _match_path(path: str, pattern: str) -> bool:
    parts = path.split(".")
    pat_parts = pattern.split(".")
    if len(parts) != len(pat_parts):
        return False
    for p, pp in zip(parts, pat_parts):
        if pp != "*" and p != pp:
            return False
    return True


def _is_non_overwritable(path: str) -> bool:
    return any(_match_path(path, pat) for pat in NON_OVERWRITABLE)


def _deep_merge(base: dict, existing: dict, path: str = "") -> dict:
    """Merge existing into base, preserving non-overwritable fields as-is.
    Arrays (features, feats, item_states) are merged by identity: name for
    features/feats, inventory_ref for item_states. Non-overwritable sub-fields
    within matched array elements are preserved from existing."""
    result = {}
    # Insertion-order-preserving union: base's keys in order, then existing-only
    # keys in existing's order. Fixes top-level and nested key order run-to-run.
    for key in list(base) + [k for k in existing if k not in base]:
        child_path = f"{path}.{key}" if path else key
        base_val = base.get(key)
        exist_val = existing.get(key)

        if _is_non_overwritable(child_path):
            if key in existing:
                result[key] = exist_val
            elif key in base:
                result[key] = base_val
        elif isinstance(base_val, list) and isinstance(exist_val, list):
            result[key] = _merge_array(base_val, exist_val, key, child_path)
        elif isinstance(base_val, dict) and isinstance(exist_val, dict):
            result[key] = _deep_merge(base_val, exist_val, child_path)
        elif key in base:
            result[key] = base_val
        else:
            result[key] = exist_val
    return result


def _merge_array(base: list, existing: list, key_name: str,
                 path: str) -> list:
    """Merge two arrays. For features/feats, match by 'name'. For item_states,
    match by 'inventory_ref'. Non-overwritable sub-fields preserved from existing."""
    id_field = {"features": "name", "feats": "name",
                "item_states": "inventory_ref"}.get(key_name)

    result = []
    existing_by_id = {}
    if id_field:
        for item in existing:
            if isinstance(item, dict) and item.get(id_field):
                existing_by_id[item[id_field]] = item

    for base_item in base:
        if not isinstance(base_item, dict):
            result.append(base_item)
            continue

        identity = base_item.get(id_field) if id_field else None
        if identity and identity in existing_by_id:
            exist_item = existing_by_id[identity]
            merged_item = {}
            for k, bv in base_item.items():
                child_path = f"{path}.{identity}.{k}"
                if _is_non_overwritable(child_path) and k in exist_item:
                    merged_item[k] = exist_item[k]
                elif isinstance(bv, dict) and isinstance(exist_item.get(k), dict):
                    merged_item[k] = _deep_merge(bv, exist_item[k], child_path)
                else:
                    merged_item[k] = bv
            for k, ev in exist_item.items():
                if k not in merged_item:
                    child_path = f"{path}.{identity}.{k}"
                    if _is_non_overwritable(child_path):
                        merged_item[k] = ev
            result.append(merged_item)
        else:
            result.append(base_item)

    if id_field:
        seen_ids = {item.get(id_field) for item in base
                    if isinstance(item, dict) and item.get(id_field)}
        for exist_item in existing:
            if (isinstance(exist_item, dict) and
                exist_item.get(id_field) and
                exist_item[id_field] not in seen_ids):
                result.append(exist_item)

    return result


# ── source-name dedup ────────────────────────────────────────────────────────


def _dedup_spell_bonuses(effects: ActiveEffects) -> ActiveEffects:
    """Same (source_name, target_kind, target_id) → keep only highest value."""
    groups = defaultdict(list)
    for b in effects.bonuses:
        key = (b.get("source_name", ""), b.get("target_kind", ""),
               b.get("target_id") or "")
        groups[key].append(b)
    deduped = []
    for group in groups.values():
        deduped.append(max(group, key=lambda b: b.get("value") or 0))
    effects.bonuses = deduped
    return effects


# ── helper: build default slot dict ──────────────────────────────────────────


def _empty_slots() -> dict:
    """A fresh empty-slot table each call — never a shared nested object, so
    callers can't mutate one another's slot dict."""
    return {"1": {"remaining": 0}}


def _default_slots(grimoire: dict | None, key: str) -> dict:
    if grimoire is None:
        return _empty_slots()
    slots = grimoire.get(key, {}) or {}
    result = {}
    for lvl, entry in slots.items():
        if isinstance(entry, dict) and _int(entry.get("max")):
            result[lvl] = {"remaining": entry["max"]}
    if not result:
        return _empty_slots()
    return result


def _default_hit_dice(core: dict) -> dict:
    hd = core.get("hit_dice", {}) or {}
    result = {}
    for die, entry in hd.items():
        if isinstance(entry, dict) and _int(entry.get("max")):
            result[die] = {"remaining": entry["max"]}
    return result


# ── orchestrator ─────────────────────────────────────────────────────────────


_TREASURE_DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")


def _treasure(starting_treasure: dict | None) -> dict:
    """A full coin purse from a (possibly partial) starting-treasure dict — every denomination present,
    defaulting to 0. ``treasure`` is generation-time state (derived from the starting-wealth rules),
    so the orchestrator seeds it here rather than re-deriving it from the final sheet."""
    src = starting_treasure if isinstance(starting_treasure, dict) else {}
    out = {}
    for d in _TREASURE_DENOMINATIONS:
        v = src.get(d)
        out[d] = v if _int(v) and v >= 0 else 0
    return out


def derive_modifier(core: dict, inventory: dict | None, grimoire: dict | None,
                    existing_modifier: dict | None, mode: str, access,
                    starting_treasure: dict | None = None) -> tuple[dict, dict]:
    """Produce a modifier-sheet:1 dict. Returns (sheet, meta).

    ``starting_treasure`` seeds the (non-overwritable) coin purse when deriving from scratch — the
    starting wealth the generation pipeline derives from the chosen equipment bundles (F05-T79).
    Absent, the purse defaults to zero. In ``fill`` mode a pre-filled purse is preserved as before."""
    meta = {"mode": mode, "derived": mode != "validate"}

    if mode == "validate":
        if existing_modifier is None:
            return {}, meta
        return dict(existing_modifier), meta

    pb = core.get("proficiency_bonus", 2)
    if not _int(pb):
        pb = 2

    states = (existing_modifier or {}).get("character_states", []) if existing_modifier else []
    item_states = (existing_modifier or {}).get("item_states", []) if existing_modifier else []
    effects = resolve_active_effects(core, inventory, states, item_states, access)
    effects = _dedup_spell_bonuses(effects)

    abilities, effective_abilities, ability_mods = derive_abilities(core, effects, access)
    armor_class, ac_detail = derive_ac(core, inventory, effects, ability_mods, access)
    speeds, speed_detail = derive_speed(core, effects, access)
    defenses = derive_defenses(core, effects, access)
    size = derive_size(core, effects, access)
    saves = derive_saving_throws(core, ability_mods, pb, effects, access)
    skills = derive_skills(core, ability_mods, pb, effects, access)
    passives = derive_passive_scores(core, skills, effects, access)
    init = derive_initiative(core, ability_mods, pb, effects, access)
    hp_eff = derive_hp_effects(core, effects, ability_mods, access)
    form_temp_pool = derive_form_temp_pool(core, effects, access)
    res_state = derive_resource_state(core, effects, access)
    attacks = derive_attacks(core, inventory, ability_mods, item_states, effects, access)
    senses = derive_senses(core, effects, access)
    features = derive_features(core, access)
    feats = derive_feats(core, access)

    core_hp_max = (core.get("hit_points", {}) or {}).get("max", 0)

    full = {
        "schema_version": 1,
        "character_id": core.get("character_id", ""),
        "character_name": core.get("character_name", ""),
        "derived_from_core": hash_core(core),
        "derived_from_grimoire": _hash_grimoire(grimoire),

        "xp": 0,
        "treasure": _treasure(starting_treasure),

        "hit_points": {
            "current": core_hp_max,
            "temp": hp_eff.get("temp", 0),
            "max_boost": hp_eff.get("max_boost", 0),
            "max_reduction": hp_eff.get("max_reduction", 0),
        },
        "death_saves": {"successes": 0, "failures": 0},
        "hit_dice": _default_hit_dice(core),
        "spell_slots": _default_slots(grimoire, "spell_slots"),
        "pact_slots": _default_slots(grimoire, "pact_slots"),

        "resource_state": {
            k: {"max": v.get("max"), "remaining": v.get("max"),
                "recharge": v.get("recharge"), "recharge_amount": None}
            for k, v in res_state.items()
        },

        "abilities": abilities,
        "saving_throws": saves,
        "skills": skills,
        "passive_scores": passives,
        "effective_senses": senses,
        "effective_defenses": defenses,
        "effective_size": size,
        "effective_abilities": effective_abilities,
        "armor_class": armor_class,
        "armor_class_detail": ac_detail,
        "initiative": init,
        "speed": speeds,
        "speed_detail": speed_detail,
        "attacks": attacks,

        "character_states": [],
        "item_states": [],
        "features": [{"name": f["name"], "uses": {"max": f.get("uses", {}).get("max"),
                                                    "remaining": None}}
                     for f in features],
        "feats": [{"name": f["name"], "uses": {"max": f.get("uses", {}).get("max"),
                                                "remaining": None}}
                  for f in feats],
        "prepared_spells": [],
    }

    # An additive field, present only while a self-transform grants a temporary form-HP pool (T108).
    if form_temp_pool is not None:
        full["hit_points"]["form_temp_pool"] = form_temp_pool

    # An additive field, present only while an active condition imposes a flat per-level D20-test
    # penalty. Absent means no penalty (0). Non-sheet-representable combat riders stay out.
    if effects.d20_penalty:
        full["d20_penalty"] = effects.d20_penalty

    if mode == "fill" and existing_modifier is not None:
        full = _deep_merge(full, existing_modifier)

    return full, meta


def _hash_grimoire(grimoire: dict | None) -> str | None:
    import hashlib, json
    if grimoire is None:
        return None
    data = {"sources": grimoire.get("sources", {}), "spells": grimoire.get("spells", [])}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
