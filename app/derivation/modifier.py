"""C-M1: MODIFIER derivation engine. Pure functions that compute MODIFIER fields from
CORE + INVENTORY + GRIMOIRE + DB + active state effects. No orchestrator, no non-overwritable
field protection, no stacking-rule enforcement — those are C-M2."""
from access.primitives import grants_for
from access.validator import abilities as abilities_q
from access.validator import creature as creature_q
from access.validator import defenses as defenses_q
from access.validator import inventory as inventory_q
from access.validator import size as size_q

# Self-transform (T60): the character temporarily BECOMES a creature (full effective-stat
# replacement). Two kinds, selected by ``detail.transform``. ``PHYSICAL`` (physical-form) replaces
# the physical ability scores only, retaining the character's MENTAL abilities and their own
# proficiencies/PB; ``FULL`` replaces all six ability scores and drops proficiencies. The mental
# ability set is a rule constant (the split is fixed by the ruleset, not a per-row DB fact).
TRANSFORM_PHYSICAL = "physical"
TRANSFORM_FULL = "full"
_TRANSFORM_KINDS = (TRANSFORM_PHYSICAL, TRANSFORM_FULL)
_MENTAL_ABILITY_IDS = frozenset({"intelligence", "wisdom", "charisma"})


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


# ── form stat-block readers (concrete creatures; pure catalog reads) ──────────


def _form_ability_scores(access, creature_id: str) -> dict:
    """The form's ability scores keyed by full DB ability id → score."""
    return {r["ability_id"]: r["score"]
            for r in creature_q.creature_abilities(access, creature_id)
            if _int(r["score"])}


def _form_speeds(access, creature_id: str) -> dict:
    """The form's movement modes keyed by mode id → feet. A mode stored as a
    ``formula_note`` (e.g. equal to the walk speed) resolves to the walk value."""
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


def _form_senses(access, creature_id: str) -> dict:
    """The form's special senses keyed by sense id → range in feet."""
    return {r["sense_id"]: r["range_ft"]
            for r in creature_q.creature_senses(access, creature_id)
            if _int(r["range_ft"])}


def _form_attacks(access, creature_id: str) -> list:
    """The form's attacks, shaped for the modifier sheet. An action counts as an attack
    when it carries an attack bonus; its damage string is the stored dice expression, or
    the flat average when no dice term is stored."""
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
            "weapon_mastery": None,
            "properties": [],
        })
    return result


def _form_defenses(access, creature_id: str) -> dict:
    """The form's effective-defences block (form is authoritative under transform)."""
    d = creature_q.creature_defenses(access, creature_id)
    return {
        "resistances": sorted(r["damage_type_id"] for r in d["resistance"] if r["damage_type_id"]),
        "immunities": sorted(r["damage_type_id"] for r in d["immunity_damage"]
                             if r["damage_type_id"]),
        "vulnerabilities": sorted(r["damage_type_id"] for r in d["vulnerability"]
                                  if r["damage_type_id"]),
        "condition_immunities": sorted(r["condition_id"] for r in d["immunity_condition"]
                                       if r["condition_id"]),
        "save_advantages": [],
        "condition_advantages": [],
    }


def _form_save_mods(access, creature_id: str) -> dict:
    """The form's stat-block saving-throw modifier per full ability id: the form's ability
    modifier plus the FORM's own proficiency bonus (``creature.pb``) for a save the form is
    proficient in (``creature_save``, T63). Empty for a form with no ability rows. Used for the
    self-transform higher-of comparison (physical) and the form-authoritative saves (full)."""
    scores = {r["ability_id"]: r["score"]
              for r in creature_q.creature_abilities(access, creature_id) if _int(r["score"])}
    proficient = {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}
    row = creature_q.creature_row(access, creature_id)
    form_pb = row["pb"] if row is not None else None
    out = {}
    for aid, score in scores.items():
        modifier = _ability_mod(score)
        if aid in proficient and _int(form_pb):
            modifier += form_pb
        out[aid] = modifier
    return out


def _form_save_proficiencies(access, creature_id: str) -> set:
    """The full ability ids the form is proficient in for saves (``creature_save``). Under a
    PHYSICAL transform the character GAINS these proficiencies and applies their OWN PB to them."""
    return {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}


def _form_skill_mods(access, creature_id: str) -> dict:
    """The form's stat-block skill modifier per skill id (``creature_skill.bonus`` — already the
    form's ability mod plus its proficiency). Used for the self-transform higher-of (physical) and
    the form-authoritative skills (full). The keys are also the form's skill proficiencies, which a
    PHYSICAL transform GAINS (applying the character's OWN PB)."""
    return {r["skill_id"]: r["bonus"]
            for r in creature_q.creature_skills(access, creature_id) if _int(r["bonus"])}


def _norm_weapon_token(token: str) -> str:
    """Canonicalise a weapon token for name/proficiency matching: lower-case, hyphens → spaces, and
    a single trailing plural 's' removed. Lets a CORE proficiency entry (which may be singular or
    plural, e.g. the plural or singular form of a weapon's name) match a weapon's name or id."""
    if not isinstance(token, str):
        return ""
    t = token.strip().lower().replace("-", " ")
    if t.endswith("s"):
        t = t[:-1]
    return t


def _weapon_proficient(weapon_profs: set, tier: str, weapon_id: str, weapon_name: str) -> bool:
    """True if the CORE weapon-proficiency list confers proficiency with this weapon, either via the
    weapon's tier (stored as '<tier> weapons') or via a specific-weapon grant matching the weapon's
    own name/id. Both sides are routed through `_norm_weapon_token`, so matching is case-insensitive
    and singular/plural-insensitive (the corpus emits lower-case tokens; the generator title-case)."""
    norm_profs = {_norm_weapon_token(p) for p in weapon_profs}
    if tier and _norm_weapon_token(f"{tier} weapons") in norm_profs:
        return True
    targets = {_norm_weapon_token(weapon_id), _norm_weapon_token(weapon_name)}
    targets.discard("")
    return bool(targets & norm_profs)


def _ability_mod(score: int) -> int:
    return (score - 10) // 2


def _mod_for_ability_id(access, abilities: dict, full_id: str) -> int:
    """Ability modifier for a canonical DB ability id, read from an `abilities` dict that may be
    keyed by CORE short codes (e.g. the short form a sheet uses) or by full DB ids. A direct
    full-id hit wins; otherwise each key is normalised (short code -> full id) and matched."""
    if full_id in abilities:
        return abilities.get(full_id) or 0
    for k, val in abilities.items():
        if abilities_q.ability_id_for_short_key(access, k) == full_id:
            return val or 0
    return 0


# ── C1: ActiveEffects resolution ─────────────────────────────────────────────


class ActiveEffects:
    def __init__(self):
        self.bonuses: list[dict] = []
        self.resistances: set[str] = set()
        self.immunities: set[str] = set()
        self.vulnerabilities: set[str] = set()
        self.condition_immunities: set[str] = set()
        self.save_advantages: set[str] = set()
        self.speed_grants: list[dict] = []
        self.ability_sets: list[dict] = []
        # Size effects: a net relative step (grow/shrink) and any absolute
        # 'set' targets (a shape-change transformation → a creature's size).
        self.size_steps: int = 0
        self.size_sets: list[str] = []
        # State-gated extra-damage riders on weapon/unarmed attacks: [{die_count,
        # die_faces, damage_type_id}].
        self.extra_damage: list[dict] = []
        self.hp_boost: int = 0
        self.hp_reduction: int = 0
        self.ac_floor: int | None = None
        self.sense_grants: list[dict] = []
        # Self-transform: {creature_id, kind} when a transform state is active
        # (concrete form only), else None. Drives full effective-stat replacement.
        self.transform: dict | None = None


def resolve_active_effects(core: dict, inventory: dict | None,
                           states: list, item_states: list, access) -> ActiveEffects:
    """Resolve all active effects from character_states[] and item_states[]. Returns
    ActiveEffects with accumulated bonuses, resistances, etc. Empty states → empty effects."""
    effects = ActiveEffects()
    # Always-on ability sets from the character's PERMANENT owners (species/feats/classes/subclasses)
    # apply unconditionally — they are not gated by an active state. This mirrors the validator's
    # independently rule-grounded owner re-derivation, so a grant_ability_set on a permanent owner
    # (not just an attuned magic item) reaches effective abilities and never trips a false
    # effective-ability mismatch (reconciliation debt (b)). Runs before the empty-state fast path so
    # a gearless, stateless build still resolves its permanent ability sets.
    _accumulate_owner_ability_sets(effects, core, access)
    has_equipped = isinstance(inventory, dict) and bool(inventory.get("equipped"))
    if not states and not item_states and not has_equipped:
        return effects

    for state in states:
        if not isinstance(state, dict):
            continue
        sname = state.get("state", "")
        source_name = state.get("source", "")
        source_type = state.get("source_type", "")

        owner_kind = _owner_kind_for_source_type(source_type)
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, source_name)
        if owner_id is None:
            continue

        _accumulate_bonuses(effects, access, owner_kind, owner_id)
        _accumulate_resistances(effects, access, owner_kind, owner_id)
        _accumulate_conditions(effects, access, owner_kind, owner_id)
        _accumulate_save_advantages(effects, access, owner_kind, owner_id)
        _accumulate_speeds(effects, access, owner_kind, owner_id)
        _accumulate_ability_sets(effects, access, owner_kind, owner_id)
        _accumulate_hp(effects, access, owner_kind, owner_id, state)
        _accumulate_senses(effects, access, owner_kind, owner_id)
        _accumulate_size(effects, access, owner_kind, owner_id, state)
        _accumulate_extra_damage(effects, access, owner_kind, owner_id, state)
        _accumulate_transform(effects, access, state)

    if inventory and isinstance(inventory, dict):
        _accumulate_item_effects(effects, access, inventory, item_states)

    return effects


def _owner_kind_for_source_type(source_type: str) -> str | None:
    return {
        "feature": "class_feature",
        "spell": "spell",
        "feat": "feat",
        "item": "magic_item",
        "condition": "condition",
        "effect": "spell",
        "class_resource": "class_resource",
        "species": "species",
    }.get(source_type)


def _accumulate_bonuses(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_bonus", owner_kind, owner_id):
        effects.bonuses.append(dict(row))


def _accumulate_resistances(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_resistance", owner_kind, owner_id):
        dtid = row["damage_type_id"]
        if dtid:
            effects.resistances.add(dtid)


def _accumulate_conditions(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_condition", owner_kind, owner_id):
        cid = row["condition_id"]
        effect = row["effect"]
        if cid and effect == "immunity":
            effects.condition_immunities.add(cid)


def _accumulate_save_advantages(effects: ActiveEffects, access, owner_kind, owner_id):
    # Map each grant to its CORE scope string (ability → abbreviation, otherwise the
    # scope keyword) so the union in derive_defenses matches CORE's representation.
    for row in grants_for(access.db, "grant_save_advantage", owner_kind, owner_id):
        scope = defenses_q.save_scope_for(access, row)
        if scope:
            effects.save_advantages.add(scope)


def _accumulate_size(effects: ActiveEffects, access, owner_kind, owner_id, state: dict):
    """Accumulate size effects from one active state. A transformation carrying
    ``detail.into`` sets size absolutely from that creature's size; otherwise the
    owner's grant_size rows apply, the row selected by matching the row's ``variant``
    to the state's declared ``detail.effect``."""
    detail = state.get("detail") if isinstance(state, dict) else None
    detail = detail if isinstance(detail, dict) else {}

    into = detail.get("into")
    if into:
        set_size = size_q.creature_size(access, into)
        if set_size:
            effects.size_sets.append(set_size)
        return

    variant = detail.get("effect")
    for row in grants_for(access.db, "grant_size", owner_kind, owner_id):
        if row["mode"] == "step":
            if variant is None or row["variant"] == variant:
                effects.size_steps += (row["step"] or 0)
        elif row["mode"] == "set" and row["size_id"]:
            effects.size_sets.append(row["size_id"])


def _accumulate_transform(effects: ActiveEffects, access, state: dict):
    """Capture a self-transform from one active state carrying ``detail.into`` +
    ``detail.transform``. The form must be a CONCRETE creature (a fixed stat block); a
    templated (owner-scaled) creature has no standalone block and is skipped gracefully,
    as is an unknown id or a missing/invalid ``transform`` kind (which leaves the legacy
    size-only ``detail.into`` behaviour untouched)."""
    detail = state.get("detail") if isinstance(state, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    into = detail.get("into")
    kind = detail.get("transform")
    if not into or kind not in _TRANSFORM_KINDS:
        return
    if creature_q.creature_row(access, into) is None:
        return
    if creature_q.creature_formulas(access, into):
        return  # templated form → no standalone stat block; skip
    effects.transform = {"creature_id": into, "kind": kind}


def _accumulate_extra_damage(effects: ActiveEffects, access, owner_kind, owner_id, state: dict):
    """Accumulate condition-gated extra-damage riders from one active state's owner.
    A grant_bonus row with ``target_kind='extra_damage'`` and a ``condition_kind`` gate
    applies only when it is ungated, or the gate matches this state's id — so a rider on
    a spell that also owns the opposite effect (e.g. shrink) does not leak to that state."""
    state_id = state.get("state") if isinstance(state, dict) else None
    for row in grants_for(access.db, "grant_bonus", owner_kind, owner_id):
        if row["target_kind"] != "extra_damage":
            continue
        gate = row["condition_kind"]
        if gate is not None and gate != state_id:
            continue
        dc, df = row["die_count"], row["die_faces"]
        if _int(dc) and _int(df):
            effects.extra_damage.append(
                {"die_count": dc, "die_faces": df, "damage_type_id": row["damage_type_id"]})


def _accumulate_speeds(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_speed", owner_kind, owner_id):
        effects.speed_grants.append(dict(row))


def _accumulate_ability_sets(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_ability_set", owner_kind, owner_id):
        if row["mode"] in ("set", "floor"):
            effects.ability_sets.append(dict(row))


def _accumulate_owner_ability_sets(effects: ActiveEffects, core: dict, access):
    """Always-on ability-set/floor grants from the character's permanent owners — species, each feat,
    each class, and each subclass — gated by class-entry level. Mirrors the validator's independently
    rule-grounded owner set (``validator.checks.modifier._owner_ability_sets``): the deriver applies
    ``grant_ability_set`` across a state-driven owner set + attuned items, so a grant on a permanent
    owner would otherwise be missed and produce a false effective-ability mismatch. No non-item grants
    exist in the reference dataset today, so this is inert there; the synthetic ruleset carries one on
    a species, which this reconciles."""
    if not isinstance(core, dict):
        return
    ident = core.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    def _collect(owner_kind: str, owner_id, at_level=None) -> None:
        """Append an owner's ability-set/floor grants, gated by ``at_level`` (None = level-agnostic)."""
        if owner_id is None:
            return
        for row in grants_for(access.db, "grant_ability_set", owner_kind, owner_id, at_level):
            if row["mode"] in ("set", "floor"):
                effects.ability_sets.append(dict(row))

    _collect("species", access.resolve("species", ident.get("species")))

    feats = core.get("feats")
    if isinstance(feats, list):
        for f in feats:
            name = f if isinstance(f, str) else (f.get("name") if isinstance(f, dict) else None)
            _collect("feat", access.resolve("feat", name))

    classes = ident.get("classes")
    if isinstance(classes, list):
        for c in classes:
            if not isinstance(c, dict):
                continue
            lvl = c.get("level")
            at = lvl if isinstance(lvl, int) and not isinstance(lvl, bool) else 0
            _collect("class", access.resolve("class", c.get("class")), at)
            sub = c.get("subclass")
            if sub:
                _collect("subclass", access.resolve("subclass", sub), at)


def _accumulate_hp(effects: ActiveEffects, access, owner_kind, owner_id, state: dict):
    """Accumulate a state's owner's HP grants. A grant_hp row applies when it is ungated
    (condition_kind None) or its condition_kind matches this state's id — mirroring the extra-damage
    rider gate so a drain owned alongside other effects does not leak across states. A positive
    amount raises the max (max_boost); a NEGATIVE amount is a drain/curse that lowers the max
    (max_reduction) — the state-gated maximum-HP reduction mechanism (F05-T58)."""
    state_id = state.get("state") if isinstance(state, dict) else None
    for row in grants_for(access.db, "grant_hp", owner_kind, owner_id):
        gate = row["condition_kind"]
        if gate is not None and gate != state_id:
            continue
        amount = (row["flat"] or 0) + (row["per_level"] or 0)
        if amount >= 0:
            effects.hp_boost += amount
        else:
            effects.hp_reduction += -amount


def _accumulate_senses(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_sense", owner_kind, owner_id):
        effects.sense_grants.append(dict(row))


def _item_name_for_ref(inventory, inv_ref):
    """Resolve an item's name from an inventory_ref (equipped slot or backpack)."""
    if not inv_ref:
        return None
    equipped = inventory.get("equipped", {}) or {}
    if isinstance(equipped, dict):
        for slot_item in equipped.values():
            if isinstance(slot_item, dict) and slot_item.get("id") == inv_ref:
                return slot_item.get("name")
    backpack = inventory.get("backpack", [])
    for bi in (backpack if isinstance(backpack, list) else []):
        if isinstance(bi, dict) and bi.get("id") == inv_ref:
            return bi.get("name")
    return None


def _accumulate_item_effects(effects: ActiveEffects, access, inventory, item_states):
    # 1) Attuned items (from item_states): full effects — bonuses, resistances,
    #    senses and speeds all materialise here.
    attuned_refs: set = set()
    if isinstance(item_states, list):
        for istate in item_states:
            if not isinstance(istate, dict) or not istate.get("attuned"):
                continue
            inv_ref = istate.get("inventory_ref")
            item_name = _item_name_for_ref(inventory, inv_ref)
            if not item_name:
                continue
            mid = access.resolve("magic_item", item_name)
            if not mid:
                continue
            if inv_ref:
                attuned_refs.add(inv_ref)
            _accumulate_bonuses(effects, access, "magic_item", mid)
            _accumulate_resistances(effects, access, "magic_item", mid)
            _accumulate_ability_sets(effects, access, "magic_item", mid)
            _accumulate_senses(effects, access, "magic_item", mid)
            _accumulate_speeds(effects, access, "magic_item", mid)

    # 2) Passive-on-equip items: a magic item that does NOT require attunement
    #    confers its sense/speed grants while equipped (no attunement needed).
    #    Attunement-gated items are handled solely by branch (1) above. An item
    #    already consumed as attuned in branch (1) must be skipped here too, or a
    #    non-attunement item flagged attuned would double-count its senses/speeds.
    equipped = inventory.get("equipped", {}) or {}
    if isinstance(equipped, dict):
        for slot_item in equipped.values():
            if not isinstance(slot_item, dict):
                continue
            if slot_item.get("id") in attuned_refs:
                continue
            item_name = slot_item.get("name")
            if not item_name:
                continue
            mid = access.resolve("magic_item", item_name)
            if not mid:
                continue
            if inventory_q.requires_attunement(access, mid):
                continue
            _accumulate_senses(effects, access, "magic_item", mid)
            _accumulate_speeds(effects, access, "magic_item", mid)


# ── C2: Derivation helpers ───────────────────────────────────────────────────


def derive_abilities(core: dict, effects: ActiveEffects, access) -> tuple[dict, dict, dict]:
    """Returns (abilities_dict, effective_abilities_dict, ability_mods_dict).
    abilities: {aid: {modifier, reduction}}
    effective_abilities: {aid: score}. A 'set' grant is a TRUE OVERRIDE of the score; a 'floor'
    grant raises it to a minimum (max)."""
    core_abilities = core.get("abilities", {}) or {}
    tf = effects.transform
    form_scores = _form_ability_scores(access, tf["creature_id"]) if tf else {}
    result = {}
    effective = {}
    mods = {}
    for aid, score_obj in core_abilities.items():
        if not isinstance(score_obj, dict):
            continue
        final_score = score_obj.get("final", 10)
        if not _int(final_score):
            final_score = 10
        reduction = 0
        override_score = None
        floor_score = None
        # `aid` is the CORE key (a short code); grant_ability_set.ability_id is the full DB id, so
        # normalise before matching a set-ability effect to this ability.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
        for ab_set in effects.ability_sets:
            if ab_set["ability_id"] in (aid, full_aid):
                s = ab_set["score"]
                if s is None:
                    continue
                if ab_set.get("mode") == "set":
                    if override_score is None or s > override_score:
                        override_score = s
                else:  # floor
                    if floor_score is None or s > floor_score:
                        floor_score = s
        eff = final_score - reduction
        if floor_score is not None:
            eff = max(eff, floor_score)
        if override_score is not None:  # 'set' overrides base and floor alike
            eff = override_score
        # Self-transform replaces the effective score with the form's: all six abilities for a
        # FULL transform, the physical abilities only for a PHYSICAL (physical-form) one — the
        # character's mental abilities (Int/Wis/Cha) are retained.
        if tf and (tf["kind"] == TRANSFORM_FULL or full_aid not in _MENTAL_ABILITY_IDS):
            form_score = form_scores.get(full_aid)
            if form_score is not None:
                eff = form_score
        modifier = _ability_mod(eff)
        result[aid] = {"modifier": modifier, "reduction": reduction}
        effective[aid] = eff
        mods[aid] = modifier
    return result, effective, mods


def derive_ac(core: dict, inventory: dict | None, effects: ActiveEffects, abilities: dict,
              access) -> tuple[int, dict]:
    """Returns (armor_class, armor_class_detail). `abilities` maps an ability key (CORE short
    code or full DB id) to its modifier; the Dex mod is resolved via that key normalisation."""
    # Under a self-transform the form's stat block is authoritative: AC is the form's
    # flat AC, no worn-armour/Dex/bonus contribution (gear melds into the new form).
    tf = effects.transform
    if tf:
        row = creature_q.creature_row(access, tf["creature_id"])
        ac = row["ac_value"] if row is not None and _int(row["ac_value"]) else 10
        detail = {"source": tf["creature_id"], "base": ac, "dex_bonus": 0,
                  "bonuses": [], "floor": None}
        return ac, detail

    dex_mod = _mod_for_ability_id(access, abilities, "dexterity")
    equipped = (inventory or {}).get("equipped", {}) or {}
    if not isinstance(equipped, dict):
        equipped = {}

    armor_item = equipped.get("armor")
    shield_item = equipped.get("shield")

    base = 10 + dex_mod
    source = "unarmored"
    dex_bonus = dex_mod
    bonuses = []
    floor = effects.ac_floor

    if isinstance(armor_item, dict) and armor_item.get("name"):
        armor_name = armor_item["name"]
        armor_id = access.resolve("catalog_item", armor_name)
        if armor_id:
            arow = access.db.one(
                "SELECT base_ac, dex_cap, ac_bonus, category_id FROM armor WHERE id=?",
                armor_id)
            if arow:
                base = (arow["base_ac"] or 10)
                cap = arow["dex_cap"]
                dex_bonus = min(dex_mod, cap) if cap is not None and cap > 0 else (
                    0 if cap == 0 else dex_mod)
                base += dex_bonus
                source = armor_id

    if isinstance(shield_item, dict) and shield_item.get("name"):
        shield_name = shield_item["name"]
        shield_id = access.resolve("catalog_item", shield_name)
        if shield_id:
            srow = access.db.one(
                "SELECT ac_bonus FROM armor WHERE id=? AND category_id='shield'", shield_id)
            if srow and srow["ac_bonus"]:
                base += srow["ac_bonus"]

    for b in effects.bonuses:
        if b["target_kind"] == "ac" and b["value"]:
            bonuses.append({"value": b["value"], "source": b.get("source_name", "")})
            base += b["value"]

    if floor is not None:
        base = max(base, floor)

    raw_base = base - dex_bonus - sum(b["value"] for b in bonuses)
    detail = {
        "source": source,
        "base": raw_base,
        "dex_bonus": dex_bonus,
        "bonuses": bonuses,
        "floor": floor,
    }
    return base, detail


def _resolve_speeds(grant_rows: list, base_walk: int, class_bonuses: list) -> dict:
    """Deriver-owned speed resolution — independent of the validator's resolver (F05-T78).

    Mirrors the CORE deriver's own resolver (F05-T67): walk starts from the base; a ``sets_total``
    grant OVERRIDES a mode (largest wins across several); an ``additive`` grant SUMS onto the mode;
    a class-resource speed bonus adds to walk; an ``equals_walk`` mode mirrors the resolved walk
    speed. Zero-valued modes are dropped so a baseless build never emits a spurious ``walk 0``.

    The deriver and the validator's movement check re-implement this rule separately: they AGREE
    because both read the same grant rows from the DB correctly, NOT because they share code — that
    independence is the whole point. The ``equals_walk`` set is iterated in ``sorted()`` order so the
    emitted key order is byte-reproducible across ``PYTHONHASHSEED`` (F05-T52). Rows are read by
    dict-style key access, so both raw grant rows and synthesised dict rows are accepted."""
    phases: dict = {"walk": base_walk or 0}
    sets_total_max: dict = {}
    additive_sum: dict = {}
    equals_walk_modes: set = set()

    for row in grant_rows:
        mode = row["movement_mode_id"]
        if row["sets_total"]:
            ft = row["feet"]
            if ft is not None:
                sets_total_max[mode] = max(sets_total_max.get(mode, 0), ft)
        elif row["additive"]:
            additive_sum[mode] = additive_sum.get(mode, 0) + (row["feet"] or 0)
        elif row["equals_walk"]:
            equals_walk_modes.add(mode)

    for mode, ft in sets_total_max.items():
        phases[mode] = ft
    for mode, ft in additive_sum.items():
        phases[mode] = phases.get(mode, 0) + ft
    if class_bonuses:
        phases["walk"] = phases.get("walk", 0) + max(class_bonuses)
    # sorted() only for a deterministic key order — an equals_walk mode mirrors the resolved walk.
    for mode in sorted(equals_walk_modes):
        if mode != "walk":
            phases[mode] = phases.get("walk", 0)

    return {k: v for k, v in phases.items() if v > 0}


def derive_speed(core: dict, effects: ActiveEffects, access) -> tuple[dict, dict]:
    """Returns (speed_dict, speed_detail).

    Speed is resolved by the deriver-owned ``_resolve_speeds`` (F05-T78) — the validator's movement
    check re-derives the same rule independently, so it provides genuine cross-checking rather than
    rubber-stamping output produced with the same code."""
    # Under a self-transform the form's speeds replace the character's entirely.
    tf = effects.transform
    if tf:
        speeds = _form_speeds(access, tf["creature_id"]) or {"walk": 0}
        detail = {"base": speeds.get("walk", 0), "base_source": tf["creature_id"],
                  "base_mode": "walk", "modifiers": []}
        return speeds, detail

    perm_speed = core.get("permanent_speed", {}) or {}
    base_walk = perm_speed.get("walk", 30)
    if not _int(base_walk):
        base_walk = 30

    all_grants = list(effects.speed_grants)
    for mode, ft in perm_speed.items():
        if mode == "walk":
            continue
        if _int(ft):
            all_grants.append({
                "movement_mode_id": mode,
                "feet": ft,
                "sets_total": 1,
                "additive": 0,
                "equals_walk": 0,
            })

    speeds = _resolve_speeds(all_grants, base_walk, [])

    detail = {
        "base": base_walk,
        "base_source": "species",
        "base_mode": "walk",
        "modifiers": [],
    }
    for g in effects.speed_grants:
        mode = g["movement_mode_id"]
        # equals_walk grants carry a NULL feet — report the resolved effective speed
        # for that mode instead of the raw (missing) value.
        value = g["feet"]
        if not _int(value):
            value = speeds.get(mode, 0)
        detail["modifiers"].append({
            "mode": mode,
            "source": g.get("owner_id", ""),
            "value": value,
        })
    return speeds, detail


def derive_defenses(core: dict, effects: ActiveEffects, access) -> dict:
    """Returns effective_defenses dict merging CORE permanent + active state grants.
    Under a self-transform the form's defences are authoritative (replace, not union)."""
    if effects.transform:
        return _form_defenses(access, effects.transform["creature_id"])

    perm = core.get("permanent_defenses", {}) or {}
    if not isinstance(perm, dict):
        perm = {}

    # Sort each set union so emitted order is stable (alphabetical by id string).
    # Only ORDER changes here; the set contents (values) are unchanged.
    result = {
        "resistances": sorted(set(perm.get("resistances", [])) | effects.resistances),
        "immunities": sorted(set(perm.get("immunities", [])) | effects.immunities),
        "vulnerabilities": sorted(set(perm.get("vulnerabilities", [])) | effects.vulnerabilities),
        "condition_immunities": sorted(
            set(perm.get("condition_immunities", [])) | effects.condition_immunities),
        "save_advantages": sorted(
            set(perm.get("save_advantages", [])) | effects.save_advantages),
        "condition_advantages": perm.get("condition_advantages", []) or [],
    }
    return result


def derive_size(core: dict, effects: ActiveEffects, access) -> str:
    """Returns effective_size. A 'set' transformation overrides absolutely (the
    largest wins on conflict); otherwise a net relative step is applied to
    CORE.identity.size, clamped to the size catalog's ordinal range."""
    ident = core.get("identity", {}) or {}
    base = ident.get("size", "medium")

    if effects.size_sets:
        return max(effects.size_sets,
                   key=lambda s: size_q.size_ordinal(access, s) or 0)

    if effects.size_steps:
        base_ord = size_q.size_ordinal(access, base)
        if base_ord is not None:
            lo, hi = size_q.size_ordinal_bounds(access)
            target = max(lo, min(hi, base_ord + effects.size_steps))
            resolved = size_q.size_by_ordinal(access, target)
            if resolved:
                return resolved
    return base


def derive_saving_throws(core: dict, abilities: dict, pb, effects: ActiveEffects,
                         access) -> dict:
    """Returns saving_throws: {aid: {modifier}}. Under a FULL transform saves are the FORM's
    stat-block saves — the form's ability modifier plus the form's own proficiency bonus where the
    form is proficient (T63), no character proficiency/PB (the form's game statistics replace the
    character's entirely). A PHYSICAL transform follows the shape-shift rule (T65): the character
    keeps their own save proficiencies AND GAINS the form's, applying their OWN proficiency bonus to
    all of them, then uses the higher of that value and the form's stat-block save."""
    tf = effects.transform
    saves = core.get("saving_throws", {}) or {}
    form_saves = _form_save_mods(access, tf["creature_id"]) if tf else {}
    form_save_prof = _form_save_proficiencies(access, tf["creature_id"]) if tf else set()
    result = {}
    for aid, ab_mod in abilities.items():
        # `aid` is the CORE key (a short code); grant target ids / form saves are full DB ids, so
        # normalise before comparing a per-ability save bonus's target or a form save to this save.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
        if tf and tf["kind"] == TRANSFORM_FULL:
            result[aid] = {"modifier": form_saves.get(full_aid, ab_mod)}
            continue
        mod = ab_mod
        save_data = saves.get(aid)
        if isinstance(save_data, dict):
            proficient = save_data.get("proficient", False)
        else:
            proficient = bool(save_data)
        # PHYSICAL transform: gain the form's save proficiencies (applied with the character's OWN PB).
        if tf and full_aid in form_save_prof:
            proficient = True
        if proficient and _int(pb):
            mod += pb
        for b in effects.bonuses:
            if b["target_kind"] == "saving_throw":
                # grant_bonus splits per-ability via target_id (NULL = every save;
                # set = that one ability's save), mirroring the validator. There is
                # no ability_id column.
                tid = b.get("target_id")
                if not tid or tid == full_aid:
                    if b["value"]:
                        mod += b["value"]
        if tf:  # PHYSICAL transform: higher of the character's own save and the form's stat block
            mod = max(mod, form_saves.get(full_aid, mod))
        result[aid] = {"modifier": mod}
    return result


def derive_skills(core: dict, abilities: dict, pb, effects: ActiveEffects,
                  access) -> dict:
    """Returns skills: {sid: {modifier}}. Under a FULL transform skills are the FORM's stat-block
    skills — the form's skill bonus where the form has that skill, else the form's ability modifier,
    with NO character proficiency/PB (the form's game statistics replace the character's entirely). A
    PHYSICAL transform follows the shape-shift rule (T65): the character keeps their own skill
    proficiencies/expertise AND GAINS the form's, applying their OWN proficiency bonus to gained
    ones, then uses the higher of that value and the form's stat-block skill bonus."""
    tf = effects.transform
    full = bool(tf and tf["kind"] == TRANSFORM_FULL)
    form_skills = _form_skill_mods(access, tf["creature_id"]) if tf else {}
    core_skills = core.get("skills", {}) or {}
    result = {}
    for sid, skill_obj in core_skills.items():
        if not isinstance(skill_obj, dict):
            continue
        sk_ability = skill_obj.get("ability", "")
        ab_mod = abilities.get(sk_ability, 0)
        # `sid` is the sheet's skill key (a display name); the form's skills are keyed by the DB
        # skill id, so resolve before looking up a form skill bonus / proficiency.
        form_sid = access.resolve("skill", sid) or sid if tf else None
        if full:
            result[sid] = {"modifier": form_skills.get(form_sid, ab_mod)}
            continue
        mod = ab_mod
        if _int(pb):
            exp = skill_obj.get("expertise", False)
            # PHYSICAL transform: gain the form's skill proficiency (own PB) in addition to own.
            prof = skill_obj.get("proficient", False) or (bool(tf) and form_sid in form_skills)
            if exp:
                mod += pb * 2
            elif prof:
                mod += pb
        if tf:  # PHYSICAL transform: higher of the character's own skill and the form's stat block
            mod = max(mod, form_skills.get(form_sid, mod))
        result[sid] = {"modifier": mod}
    return result


def derive_passive_scores(core: dict, skills: dict, effects: ActiveEffects,
                          access) -> dict:
    """Returns passive_scores: {sid: 10 + skill_modifier}."""
    result = {}
    for sid, data in skills.items():
        result[sid] = 10 + (data.get("modifier", 0) if isinstance(data, dict) else 0)
    return result


def derive_initiative(core: dict, abilities: dict, pb, effects: ActiveEffects,
                      access) -> int:
    """Returns initiative modifier: Dex mod + bonuses from states. `abilities` may be keyed by a
    CORE short code, so resolve the Dex mod via the same key normalisation as AC/attacks."""
    dex_mod = _mod_for_ability_id(access, abilities, "dexterity")
    return dex_mod


def derive_hp_effects(core: dict, effects: ActiveEffects, ability_mods: dict, access) -> dict:
    """Returns hit_points effects: {max_boost, max_reduction}.

    Beyond the state-driven hp_boost/hp_reduction, the effective-CON change recomputes max HP as a
    DELTA on those fields (the modifier sheet has no absolute max; effective max = CORE max +
    max_boost − max_reduction). With ``core_con_mod`` from CORE.abilities and ``eff_con_mod`` the
    already-derived effective CON modifier, ``hp_delta = (eff_con_mod − core_con_mod) × total_level``
    adds max(0, hp_delta) to max_boost (on top of the state hp_boost) and max(0, −hp_delta) to
    max_reduction."""
    from validator.checks.vitals import CON_ABBREV

    # Under a self-transform the character retains their OWN Hit Points/Hit Dice, so the
    # effective-CON change from the form does NOT recompute max HP (the form's HP is a
    # separate live-play Temporary-HP pool, not derived here — T60 fork 2). Only any state
    # grant_hp (none for a transform state) still applies.
    if effects.transform:
        return {"max_boost": effects.hp_boost, "max_reduction": effects.hp_reduction}

    core_abilities = core.get("abilities", {}) or {}
    con_id = abilities_q.ability_id(access, CON_ABBREV)
    core_con_mod = 0
    eff_con_mod = 0
    if con_id is not None and isinstance(core_abilities, dict):
        for k, score_obj in core_abilities.items():
            if abilities_q.ability_id(access, k) != con_id:
                continue
            if isinstance(score_obj, dict):
                final = score_obj.get("final", 10)
                if _int(final):
                    core_con_mod = _ability_mod(final)
            eff_con_mod = ability_mods.get(k, core_con_mod)
            if not _int(eff_con_mod):
                eff_con_mod = core_con_mod
            break

    ident = core.get("identity", {}) or {}
    classes = ident.get("classes", []) if isinstance(ident, dict) else []
    total_level = 0
    if isinstance(classes, list):
        for c in classes:
            if isinstance(c, dict) and _int(c.get("level")):
                total_level += c["level"]

    hp_delta = (eff_con_mod - core_con_mod) * total_level
    return {
        "max_boost": effects.hp_boost + max(0, hp_delta),
        "max_reduction": effects.hp_reduction + max(0, -hp_delta),
    }


def derive_resource_state(core: dict, effects: ActiveEffects, access) -> dict:
    """Returns resource_state dict from CORE.resource_budgets."""
    budgets = core.get("resource_budgets", {}) or {}
    result = {}
    for key, budget in budgets.items():
        if not isinstance(budget, dict):
            continue
        mx = budget.get("max")
        result[key] = {
            "max": mx,
            "recharge": None,
            "recharge_amount": None,
        }
    return result


def derive_attacks(core: dict, inventory: dict | None, abilities: dict,
                   item_states: list, effects: ActiveEffects, access) -> list[dict]:
    """Returns attacks: list of attack row dicts for each equipped weapon.

    Extra-damage riders append their own die term to a weapon's damage string via the existing
    signed formatter. Two sources fold in: state-gated riders (``effects.extra_damage``) apply to
    every weapon attack; an item-owned rider (a weapon-backed magic item owning exactly one
    ``extra_damage`` grant, active per attunement/equip) folds only into THAT item's own attack.

    A subtractive rider (negative die_count, e.g. a shrink effect → ``-1d4``) is emitted raw; the
    "damage not below 1" floor such an effect may carry is applied at the render/roll layer on the
    rolled total, and is intentionally not encoded in the static dice string.

    Under a self-transform the character's attacks are the form's actions (gear melds into the
    new form); the equipped-weapon attacks below do not apply."""
    if effects.transform:
        return _form_attacks(access, effects.transform["creature_id"])

    equipped = (inventory or {}).get("equipped", {}) or {}
    if not isinstance(equipped, dict):
        return []

    profs = core.get("proficiencies", {}) or {}
    weapon_profs = set(profs.get("weapons", [])) if isinstance(profs, dict) else set()
    pb = core.get("proficiency_bonus", 0)
    masteries = set(core.get("weapon_masteries", []) or [])

    # Attuned inventory refs (for gating an attunement-requiring item's own rider).
    attuned_refs = {ist.get("inventory_ref") for ist in (item_states or [])
                    if isinstance(ist, dict) and ist.get("attuned")}

    attacks = []
    for slot in ("main_hand", "off_hand"):
        item = equipped.get(slot)
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue

        weapon_id = access.resolve("catalog_item", name)
        if weapon_id is None:
            continue

        # `stats_id` is the id whose base weapon-stats row (dice/tier/properties) drives the attack.
        # For a mundane weapon it is the weapon itself; for a magic weapon catalogued without its own
        # stats row it resolves to the underlying base weapon (F05-T56), so the attack still
        # materialises. Proficiency and the item-owned rider keep matching on the magic item's own
        # id/name below.
        stats_id = weapon_id
        wrow = access.db.one(
            "SELECT tier_id, range_class_id, dmg_dice_count, dmg_die_faces, "
            "dmg_flat, damage_type_id, mastery_id FROM weapon WHERE id=?", stats_id)
        if wrow is None:
            base_id = inventory_q.base_weapon_id_for_item(access, weapon_id)
            if base_id is None:
                continue
            stats_id = base_id
            wrow = access.db.one(
                "SELECT tier_id, range_class_id, dmg_dice_count, dmg_die_faces, "
                "dmg_flat, damage_type_id, mastery_id FROM weapon WHERE id=?", stats_id)
            if wrow is None:
                continue

        props = _weapon_properties(access, stats_id)
        tier = wrow["tier_id"] or ""
        is_ranged = wrow["range_class_id"] == "ranged"
        is_finesse = "finesse" in props
        is_two_handed = "two-handed" in props

        str_mod = _mod_for_ability_id(access, abilities, "strength")
        dex_mod = _mod_for_ability_id(access, abilities, "dexterity")
        if is_finesse:
            ab_mod = max(str_mod, dex_mod)
        elif is_ranged:
            ab_mod = dex_mod
        else:
            ab_mod = str_mod

        bonus = ab_mod
        if _int(pb) and _weapon_proficient(weapon_profs, tier, weapon_id, name):
            bonus += pb

        for b in effects.bonuses:
            if b["target_kind"] == "weapon_attack" and b["value"]:
                bonus += b["value"]

        dmg_flat = wrow["dmg_flat"] or 0
        dmg_count = wrow["dmg_dice_count"] or 1
        dmg_faces = wrow["dmg_die_faces"] or 4

        dmg_bonus = ab_mod + dmg_flat
        for b in effects.bonuses:
            if b["target_kind"] == "weapon_damage" and b["value"]:
                dmg_bonus += b["value"]

        damage = f"{dmg_count}d{dmg_faces}"
        if dmg_bonus > 0:
            damage += f"+{dmg_bonus}"
        elif dmg_bonus < 0:
            damage += str(dmg_bonus)

        # State-gated extra-damage riders append their own die term to the damage
        # string, consistent with how the flat bonus is formatted. A negative die_count
        # is a subtractive rider (e.g. a shrink effect → "-1d4"); the "not below 1" floor
        # such an effect may carry is a runtime clamp, not encodable in the static term
        # (see the function docstring).
        for xd in effects.extra_damage:
            dc = xd.get("die_count")
            df = xd.get("die_faces")
            if _int(dc) and _int(df) and dc != 0:
                sign = "+" if dc > 0 else "-"
                damage += f"{sign}{abs(dc)}d{df}"

        # Item-owned rider: this equipped weapon's OWN single-row, weapon-backed magic item folds
        # its extra_damage die into THIS attack only (never character-wide), when active — attuned
        # if the item requires attunement, else equipped (mirrors _accumulate_item_effects).
        mid = access.resolve("magic_item", name)
        if mid is not None:
            xd_rows = inventory_q.extra_damage_grants(access, "magic_item", mid)
            # Select the single UNGATED item rider (F05-T57): an item may own several extra-damage
            # rows (a base rider plus condition-gated variants); the condition_kind gate is the
            # disambiguator. The gated rows are state-scoped (they belong to the state path, mirroring
            # that path's discipline), so an always-on item attack folds exactly the one ungated row.
            # More than one ungated row is still ambiguous and folds nothing (never silently summed).
            ungated = [r for r in xd_rows if r["condition_kind"] is None]
            if len(ungated) == 1:
                dc, df = ungated[0]["die_count"], ungated[0]["die_faces"]
                if _int(dc) and _int(df) and dc != 0:
                    active = (item.get("id") in attuned_refs
                              if inventory_q.requires_attunement(access, mid) else True)
                    if active:
                        sign = "+" if dc > 0 else "-"
                        damage += f"{sign}{abs(dc)}d{df}"

        mastery = wrow["mastery_id"]
        if mastery and mastery not in masteries:
            mastery = None

        attacks.append({
            "name": name,
            "attack_bonus": bonus,
            "damage": damage,
            "damage_type": wrow["damage_type_id"],
            "weapon_mastery": mastery,
            "properties": sorted(props),
        })

    return attacks


def _weapon_properties(access, weapon_id: str) -> set[str]:
    rows = access.db.q(
        "SELECT wpv.id FROM weapon_property_map wpm "
        "JOIN weapon_property_vocab wpv ON wpm.property_id=wpv.id "
        "WHERE wpm.weapon_id=?", weapon_id)
    return {r["id"] for r in rows}


def derive_senses(core: dict, effects: ActiveEffects, access) -> dict:
    """Returns effective_senses: {sense_id: range_ft} from CORE permanent + active grants.
    Under a self-transform the form's senses replace the character's entirely."""
    if effects.transform:
        return _form_senses(access, effects.transform["creature_id"])

    perm = core.get("permanent_senses", {}) or {}
    if not isinstance(perm, dict):
        perm = {}

    result = {}
    for k, v in perm.items():
        if _int(v):
            result[k] = v

    for g in effects.sense_grants:
        sid = g["sense_id"]
        rng = g["range_ft"]
        if sid and rng:
            current = result.get(sid, 0)
            result[sid] = max(current, rng)

    return result


def derive_features(core: dict, access) -> list[dict]:
    """Returns features: [{name, uses}] copied from CORE with uses populated from DB."""
    core_features = core.get("features", []) or []
    result = []
    for f in core_features:
        if not isinstance(f, dict):
            continue
        name = f.get("name", "")
        uses = {"max": None}
        result.append({"name": name, "uses": uses})
    return result


def derive_feats(core: dict, access) -> list[dict]:
    """Returns feats: [{name, uses}] copied from CORE with uses populated from DB."""
    core_feats = core.get("feats", []) or []
    result = []
    for f in core_feats:
        if isinstance(f, str):
            result.append({"name": f, "uses": {"max": None}})
        elif isinstance(f, dict):
            result.append({"name": f.get("name", ""), "uses": {"max": None}})
    return result
