"""C-M1: MODIFIER derivation engine. Pure functions that compute MODIFIER fields from
CORE + INVENTORY + GRIMOIRE + DB + active state effects. No orchestrator, no non-overwritable
field protection, no stacking-rule enforcement — those are C-M2."""
from access.primitives import grants_for
from access.validator import abilities as abilities_q
from access.validator import defenses as defenses_q
from access.validator import inventory as inventory_q
from access.validator import size as size_q


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


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


def resolve_active_effects(core: dict, inventory: dict | None,
                           states: list, item_states: list, access) -> ActiveEffects:
    """Resolve all active effects from character_states[] and item_states[]. Returns
    ActiveEffects with accumulated bonuses, resistances, etc. Empty states → empty effects."""
    effects = ActiveEffects()
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
        _accumulate_hp(effects, access, owner_kind, owner_id)
        _accumulate_senses(effects, access, owner_kind, owner_id)
        _accumulate_size(effects, access, owner_kind, owner_id, state)
        _accumulate_extra_damage(effects, access, owner_kind, owner_id, state)

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


def _accumulate_hp(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_hp", owner_kind, owner_id):
        effects.hp_boost += (row["flat"] or 0) + (row["per_level"] or 0)


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
        modifier = _ability_mod(eff)
        result[aid] = {"modifier": modifier, "reduction": reduction}
        effective[aid] = eff
        mods[aid] = modifier
    return result, effective, mods


def derive_ac(core: dict, inventory: dict | None, effects: ActiveEffects, abilities: dict,
              access) -> tuple[int, dict]:
    """Returns (armor_class, armor_class_detail). `abilities` maps an ability key (CORE short
    code or full DB id) to its modifier; the Dex mod is resolved via that key normalisation."""
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


def derive_speed(core: dict, effects: ActiveEffects, access) -> tuple[dict, dict]:
    """Returns (speed_dict, speed_detail).
    Reuses the _resolve_speeds algorithm from validator/checks/movement.py."""
    from validator.checks.movement import _resolve_speeds

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
    """Returns effective_defenses dict merging CORE permanent + active state grants."""
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
    """Returns saving_throws: {aid: {modifier}}."""
    saves = core.get("saving_throws", {}) or {}
    result = {}
    for aid, ab_mod in abilities.items():
        # `aid` is the CORE key (a short code); grant target ids are full DB ids, so normalise
        # before comparing a per-ability save bonus's target to this save.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
        mod = ab_mod
        save_data = saves.get(aid)
        if isinstance(save_data, dict):
            proficient = save_data.get("proficient", False)
        else:
            proficient = bool(save_data)
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
        result[aid] = {"modifier": mod}
    return result


def derive_skills(core: dict, abilities: dict, pb, effects: ActiveEffects,
                  access) -> dict:
    """Returns skills: {sid: {modifier}}."""
    core_skills = core.get("skills", {}) or {}
    result = {}
    for sid, skill_obj in core_skills.items():
        if not isinstance(skill_obj, dict):
            continue
        sk_ability = skill_obj.get("ability", "")
        ab_mod = abilities.get(sk_ability, 0)
        mod = ab_mod
        if _int(pb):
            prof = skill_obj.get("proficient", False)
            exp = skill_obj.get("expertise", False)
            if exp:
                mod += pb * 2
            elif prof:
                mod += pb
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
    rolled total, and is intentionally not encoded in the static dice string."""
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

        wrow = access.db.one(
            "SELECT tier_id, range_class_id, dmg_dice_count, dmg_die_faces, "
            "dmg_flat, damage_type_id, mastery_id FROM weapon WHERE id=?", weapon_id)
        if wrow is None:
            continue

        props = _weapon_properties(access, weapon_id)
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
            # Fold only an ungated single-row item rider — a condition_kind-gated item rider is
            # state-scoped and belongs to the state path (mirrors that path's discipline); none
            # exist today, so this is behaviour-preserving.
            if len(xd_rows) == 1 and xd_rows[0]["condition_kind"] is None:
                dc, df = xd_rows[0]["die_count"], xd_rows[0]["die_faces"]
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
    """Returns effective_senses: {sense_id: range_ft} from CORE permanent + active grants."""
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
