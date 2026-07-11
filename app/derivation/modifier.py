"""C-M1: MODIFIER derivation engine. Pure functions that compute MODIFIER fields from
CORE + INVENTORY + GRIMOIRE + DB + active state effects. No orchestrator, no non-overwritable
field protection, no stacking-rule enforcement — those are C-M2."""
from access.primitives import grants_for


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ability_mod(score: int) -> int:
    return (score - 10) // 2


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
        self.size_override: str | None = None
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
    for row in grants_for(access.db, "grant_save_advantage", owner_kind, owner_id):
        aid = row["ability_id"]
        if aid:
            effects.save_advantages.add(aid)


def _accumulate_speeds(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_speed", owner_kind, owner_id):
        effects.speed_grants.append(dict(row))


def _accumulate_ability_sets(effects: ActiveEffects, access, owner_kind, owner_id):
    for row in grants_for(access.db, "grant_ability_set", owner_kind, owner_id):
        if row["mode"] == "set":
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
            requires = access.db.scalar(
                "SELECT requires_attunement FROM magic_item WHERE id=?", mid)
            if requires:
                continue
            _accumulate_senses(effects, access, "magic_item", mid)
            _accumulate_speeds(effects, access, "magic_item", mid)


# ── C2: Derivation helpers ───────────────────────────────────────────────────


def derive_abilities(core: dict, effects: ActiveEffects, access) -> tuple[dict, dict, dict]:
    """Returns (abilities_dict, effective_abilities_dict, ability_mods_dict).
    abilities: {aid: {modifier, reduction}}
    effective_abilities: {aid: score}  — max(final - reduction, set_score)"""
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
        set_score = None
        for ab_set in effects.ability_sets:
            if ab_set["ability_id"] == aid:
                s = ab_set["score"]
                if s is not None and (set_score is None or s > set_score):
                    set_score = s
        eff = final_score - reduction
        if set_score is not None:
            eff = max(eff, set_score)
        modifier = _ability_mod(eff)
        result[aid] = {"modifier": modifier, "reduction": reduction}
        effective[aid] = eff
        mods[aid] = modifier
    return result, effective, mods


def derive_ac(core: dict, inventory: dict | None, effects: ActiveEffects, abilities: dict,
              access) -> tuple[int, dict]:
    """Returns (armor_class, armor_class_detail). abilities is keyed by DB ability ID."""
    dex_mod = abilities.get("dexterity", _find_ability_mod(access, abilities, "dexterity"))
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


def _find_ability_mod(access, abilities: dict, ability_name: str) -> int:
    aid = access.resolve("ability", ability_name)
    if aid and aid in abilities:
        return abilities.get(aid, 0)
    return 0


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

    result = {
        "resistances": list(set(perm.get("resistances", [])) | effects.resistances),
        "immunities": list(set(perm.get("immunities", [])) | effects.immunities),
        "vulnerabilities": list(set(perm.get("vulnerabilities", [])) | effects.vulnerabilities),
        "condition_immunities": list(
            set(perm.get("condition_immunities", [])) | effects.condition_immunities),
        "save_advantages": list(
            set(perm.get("save_advantages", [])) | effects.save_advantages),
        "condition_advantages": perm.get("condition_advantages", []) or [],
    }
    return result


def derive_size(core: dict, effects: ActiveEffects, access) -> str:
    """Returns effective_size: effects.size_override or CORE.identity.size."""
    if effects.size_override:
        return effects.size_override
    ident = core.get("identity", {}) or {}
    return ident.get("size", "medium")


def derive_saving_throws(core: dict, abilities: dict, pb, effects: ActiveEffects,
                         access) -> dict:
    """Returns saving_throws: {aid: {modifier}}."""
    saves = core.get("saving_throws", {}) or {}
    result = {}
    for aid, ab_mod in abilities.items():
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
                if not tid or tid == aid:
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
    """Returns initiative modifier: Dex mod + bonuses from states."""
    dex_mod = abilities.get("dexterity", 0)
    return dex_mod


def derive_hp_effects(core: dict, effects: ActiveEffects, access) -> dict:
    """Returns hit_points effects: {max_boost, max_reduction}."""
    return {
        "max_boost": effects.hp_boost,
        "max_reduction": effects.hp_reduction,
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
    """Returns attacks: list of attack row dicts for each equipped weapon."""
    equipped = (inventory or {}).get("equipped", {}) or {}
    if not isinstance(equipped, dict):
        return []

    profs = core.get("proficiencies", {}) or {}
    weapon_profs = set(profs.get("weapons", [])) if isinstance(profs, dict) else set()
    pb = core.get("proficiency_bonus", 0)
    masteries = set(core.get("weapon_masteries", []) or [])

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

        if is_finesse:
            ab_mod = max(abilities.get("strength", 0), abilities.get("dexterity", 0))
        elif is_ranged:
            ab_mod = abilities.get("dexterity", 0)
        else:
            ab_mod = abilities.get("strength", 0)

        bonus = ab_mod
        if _int(pb) and tier in weapon_profs:
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
