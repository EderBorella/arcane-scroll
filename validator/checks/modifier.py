"""MODIFIER domain (modifier-sheet:1 shape): validates a modifier sheet against DB facts +
CORE/INVENTORY/GRIMOIRE inputs. Checks cover AC, saves, skills, attacks, effective abilities,
passives, defenses, features, feats, state compatibility, prepared spells, and stacking-rule
enforcement. NOT in ALL_CHECKS — modifier:1-specific."""
from access.validator import abilities as abilities_q
from access.validator import defenses as defenses_q
from access.validator import inventory as inventory_q
from access.validator import size as size_q
from access.validator.state_compatibility import blocked_states
from validator.report import Violation

DOMAIN = "modifier"


def _owner_kind_for_source_type(source_type: str) -> str | None:
    """Map a character_state's source_type to the grant owner_kind it resolves against.
    Re-derived here so the MODIFIER checks stay independent of the deriver."""
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


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _norm_weapon_token(token: str) -> str:
    """Canonicalise a weapon token for name/proficiency matching: lower-case, hyphens → spaces, and
    a single trailing plural 's' removed. Lets a CORE proficiency entry (which may be singular or
    plural, e.g. 'rapiers' / 'rapier') match a weapon's name or id ('Rapier' / 'rapier')."""
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


def _mod_for_ability(access, mod_abilities: dict, full_id: str) -> int:
    """Ability modifier for a canonical DB ability id, read from a MODIFIER `abilities` dict that may
    be keyed by CORE short codes (an ability's abbrev) or by full DB ids. A direct full-id hit wins;
    otherwise each key is normalised (short code → full id) before matching."""
    if not isinstance(mod_abilities, dict):
        return 0
    direct = mod_abilities.get(full_id)
    if isinstance(direct, dict) and _int(direct.get("modifier")):
        return direct["modifier"]
    for key, data in mod_abilities.items():
        if not isinstance(data, dict):
            continue
        if abilities_q.ability_id_for_short_key(access, key) == full_id:
            return data.get("modifier", 0) or 0
    return 0


# ── AC checks ────────────────────────────────────────────────────────────────


def _check_ac(sheet: dict, v: list[Violation]) -> None:
    mod = sheet.get("modifier", {})
    ac = mod.get("armor_class")
    detail = mod.get("armor_class_detail")
    if not _int(ac) or not isinstance(detail, dict):
        return

    base = detail.get("base", 0)
    dex = detail.get("dex_bonus", 0)
    bonuses = detail.get("bonuses", [])
    floor = detail.get("floor")

    expected = base + dex
    if isinstance(bonuses, list):
        for b in bonuses:
            if isinstance(b, dict) and _int(b.get("value")):
                expected += b["value"]
    if floor is not None and _int(floor):
        expected = max(expected, floor)

    if ac != expected:
        v.append(Violation(DOMAIN, "ac-mismatch", "illegal",
                           f"armor_class {ac} != expected {expected}", "armor_class"))


def _check_ac_bonus_dedup(sheet: dict, v: list[Violation]) -> None:
    mod = sheet.get("modifier", {})
    detail = mod.get("armor_class_detail")
    if not isinstance(detail, dict):
        return
    bonuses = detail.get("bonuses", [])
    if not isinstance(bonuses, list):
        return
    seen = {}
    for i, b in enumerate(bonuses):
        if not isinstance(b, dict):
            continue
        src = b.get("source", "")
        if src and src in seen:
            v.append(Violation(DOMAIN, "ac-bonus-duplicate-source", "illegal",
                               f"duplicate AC bonus source {src!r}", "armor_class_detail.bonuses"))
        seen[src] = True


# ── saving throws ────────────────────────────────────────────────────────────


def _item_name_for_ref(inventory: dict, inv_ref) -> str | None:
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


def _item_save_bonuses(sheet: dict, access) -> tuple[int, dict]:
    """Save bonuses granted by attuned magic items, read straight from the DB.

    Returns ``(all_saves_bonus, per_ability_bonus)``.  A ``grant_bonus`` row with
    ``target_kind='saving_throw'`` and a NULL ``target_id`` applies to every save
    (two such items stack — +1 and +1 give +2); a row with an ability-specific
    ``target_id`` applies only to that ability's save."""
    all_bonus = 0
    per: dict[str, int] = {}
    mod = sheet.get("modifier", {}) or {}
    inventory = sheet.get("inventory", {}) or {}
    if not isinstance(inventory, dict):
        inventory = {}
    item_states = mod.get("item_states", []) or []
    if not isinstance(item_states, list):
        return 0, {}

    for istate in item_states:
        if not isinstance(istate, dict) or not istate.get("attuned"):
            continue
        name = _item_name_for_ref(inventory, istate.get("inventory_ref"))
        if not name:
            continue
        mid = access.resolve("magic_item", name)
        if not mid:
            continue
        rows = access.db.q(
            "SELECT target_id, value FROM grant_bonus "
            "WHERE owner_kind='magic_item' AND owner_id=? AND target_kind='saving_throw'", mid)
        for r in rows:
            val = r["value"] or 0
            if r["target_id"]:
                per[r["target_id"]] = per.get(r["target_id"], 0) + val
            else:
                all_bonus += val
    return all_bonus, per


def _check_saves(sheet: dict, access, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_saves = core.get("saving_throws", {}) or {}
    pb = core.get("proficiency_bonus", 0)
    core_abilities = core.get("abilities", {}) or {}
    mod_saves = mod.get("saving_throws", {}) or {}
    mod_abilities = mod.get("abilities", {}) or {}
    if not isinstance(core_saves, dict) or not isinstance(mod_saves, dict):
        return

    item_all_bonus, item_per_ability = _item_save_bonuses(sheet, access)

    for aid, save_obj in mod_saves.items():
        if not isinstance(save_obj, dict):
            continue
        actual = save_obj.get("modifier")
        if not _int(actual):
            continue

        core_save = core_saves.get(aid)
        if isinstance(core_save, dict):
            proficient = core_save.get("proficient", False)
        else:
            proficient = bool(core_save)
        ab_data = mod_abilities.get(aid, {}) or {}
        ab_mod = ab_data.get("modifier", 0)

        expected = ab_mod
        if proficient and _int(pb):
            expected += pb
        # `aid` is the MODIFIER save key (a short code); per-ability item bonuses are keyed by the
        # grant's target_id (a full DB id), so normalise before matching.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
        expected += item_all_bonus + item_per_ability.get(full_aid, 0)

        if actual != expected:
            v.append(Violation(DOMAIN, "save-modifier-mismatch", "illegal",
                               f"{aid}: modifier {actual} != expected {expected}",
                               f"saving_throws.{aid}.modifier"))


# ── skills ───────────────────────────────────────────────────────────────────


def _check_skills(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_skills = core.get("skills", {}) or {}
    pb = core.get("proficiency_bonus", 0)
    mod_abilities = mod.get("abilities", {}) or {}
    mod_skills = mod.get("skills", {}) or {}
    if not isinstance(mod_skills, dict):
        return

    for sid, skill_obj in mod_skills.items():
        if not isinstance(skill_obj, dict):
            continue
        actual = skill_obj.get("modifier")
        if not _int(actual):
            continue

        core_skill = core_skills.get(sid, {}) or {}
        if not isinstance(core_skill, dict):
            core_skill = {}
        sk_ability = core_skill.get("ability", "")
        ab_data = mod_abilities.get(sk_ability, {}) or {}
        ab_mod = ab_data.get("modifier", 0)
        expected = ab_mod
        if _int(pb):
            if core_skill.get("expertise"):
                expected += pb * 2
            elif core_skill.get("proficient"):
                expected += pb

        if actual != expected:
            v.append(Violation(DOMAIN, "skill-modifier-mismatch", "illegal",
                               f"{sid}: modifier {actual} != expected {expected}",
                               f"skills.{sid}.modifier"))


# ── attacks ──────────────────────────────────────────────────────────────────


def _item_weapon_attack_bonus(sheet: dict, access) -> int:
    """Total attack bonus granted by attuned magic items, read straight from the DB.

    Sums every ``grant_bonus`` row with ``target_kind='weapon_attack'`` over the attuned items
    (mirrors `_item_save_bonuses`). These apply to every weapon attack, matching the deriver."""
    total = 0
    mod = sheet.get("modifier", {}) or {}
    inventory = sheet.get("inventory", {}) or {}
    if not isinstance(inventory, dict):
        inventory = {}
    item_states = mod.get("item_states", []) or []
    if not isinstance(item_states, list):
        return 0

    for istate in item_states:
        if not isinstance(istate, dict) or not istate.get("attuned"):
            continue
        name = _item_name_for_ref(inventory, istate.get("inventory_ref"))
        if not name:
            continue
        mid = access.resolve("magic_item", name)
        if not mid:
            continue
        total += sum(inventory_q.weapon_attack_item_bonuses(access, mid))
    return total


def _check_attacks(sheet: dict, access, v: list[Violation]) -> None:
    """Re-derive each attack's bonus independently: ability mod (finesse → max(str,dex); ranged →
    dex; else str) + PB when proficient (tier OR specific-weapon grant) + attuned-item bonuses."""
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    attacks = mod.get("attacks", []) or []
    if not isinstance(attacks, list) or not attacks:
        return

    inventory = sheet.get("inventory", {}) or {}
    if not isinstance(inventory, dict):
        inventory = {}
    profs = core.get("proficiencies", {}) or {}
    weapon_profs = set(profs.get("weapons", [])) if isinstance(profs, dict) else set()
    pb = core.get("proficiency_bonus", 0)
    mod_abilities = mod.get("abilities", {}) or {}
    item_attack_bonus = _item_weapon_attack_bonus(sheet, access)

    for atk in attacks:
        if not isinstance(atk, dict):
            continue
        actual = atk.get("attack_bonus")
        if not _int(actual):
            continue
        name = atk.get("name")
        if not name:
            continue
        weapon_id = access.resolve("catalog_item", name)
        if weapon_id is None:
            continue
        facts = inventory_q.weapon_attack_facts(access, weapon_id)
        if facts is None:
            continue

        tier = facts["tier_id"] or ""
        is_ranged = facts["range_class_id"] == "ranged"
        is_finesse = facts["finesse"]
        str_mod = _mod_for_ability(access, mod_abilities, "strength")
        dex_mod = _mod_for_ability(access, mod_abilities, "dexterity")
        if is_finesse:
            ab_mod = max(str_mod, dex_mod)
        elif is_ranged:
            ab_mod = dex_mod
        else:
            ab_mod = str_mod

        expected = ab_mod
        if _int(pb) and _weapon_proficient(weapon_profs, tier, weapon_id, name):
            expected += pb
        expected += item_attack_bonus

        if actual != expected:
            v.append(Violation(DOMAIN, "attack-bonus-mismatch", "illegal",
                               f"{name}: attack bonus {actual} != expected {expected}",
                               "attacks"))


def _check_attack_damage(sheet: dict, access, v: list[Violation]) -> None:
    """Independently re-derive state-gated extra-damage riders from the DB and assert each
    appears in the relevant attacks' ``damage`` string. Grounded in the DB (active state →
    owner → condition-gated extra_damage grant), not the deriver's output."""
    mod = sheet.get("modifier", {})
    attacks = mod.get("attacks", []) or []
    states = mod.get("character_states", []) or []
    if not isinstance(attacks, list) or not attacks or not isinstance(states, list):
        return

    # De-dup: two active states can yield the same rider term; we assert its presence
    # once, not once per contributing state (which would emit duplicate violations).
    terms: list[str] = []
    seen_terms: set[str] = set()
    for st in states:
        if not isinstance(st, dict):
            continue
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if owner_id is None:
            continue
        state_id = st.get("state")
        for row in inventory_q.extra_damage_grants(access, owner_kind, owner_id):
            gate = row["condition_kind"]
            if gate is not None and gate != state_id:
                continue
            dc, df = row["die_count"], row["die_faces"]
            if _int(dc) and _int(df) and dc != 0:
                sign = "+" if dc > 0 else "-"
                term = f"{sign}{abs(dc)}d{df}"
                if term not in seen_terms:
                    seen_terms.add(term)
                    terms.append(term)

    if not terms:
        return

    # The deriver folds these riders only into WEAPON attacks (entries produced from an
    # equipped weapon). Scope the assertion the same way — resolve each attack's name to a
    # weapon and skip anything that isn't one (a spell/unarmed entry the deriver never folded
    # a rider into) so a non-weapon attack can't false-positive rider-missing.
    for atk in attacks:
        if not isinstance(atk, dict):
            continue
        damage = atk.get("damage")
        name = atk.get("name")
        if not isinstance(damage, str) or not damage or not name:
            continue
        weapon_id = access.resolve("catalog_item", name)
        if weapon_id is None or inventory_q.weapon_attack_facts(access, weapon_id) is None:
            continue
        for term in terms:
            if term not in damage:
                v.append(Violation(DOMAIN, "attack-damage-rider-missing", "incomplete",
                                   f"{name}: expected extra-damage rider {term} from "
                                   f"active state, not in damage {damage!r}", "attacks"))


# ── effective abilities ──────────────────────────────────────────────────────


def _item_ability_sets(sheet: dict, access) -> dict[str, list[tuple[str, int]]]:
    """Ability-set/floor grants from attuned magic items, keyed by full DB ability id.

    Returns ``{ability_id: [(mode, score), ...]}`` where ``mode`` is 'set' or 'floor'. Mirrors
    `_item_save_bonuses`: walk the attuned item_states, resolve each to a magic item, and read its
    grant_ability_set rows straight from the DB via the access layer."""
    out: dict[str, list[tuple[str, int]]] = {}
    mod = sheet.get("modifier", {}) or {}
    inventory = sheet.get("inventory", {}) or {}
    if not isinstance(inventory, dict):
        inventory = {}
    item_states = mod.get("item_states", []) or []
    if not isinstance(item_states, list):
        return out

    for istate in item_states:
        if not isinstance(istate, dict) or not istate.get("attuned"):
            continue
        name = _item_name_for_ref(inventory, istate.get("inventory_ref"))
        if not name:
            continue
        mid = access.resolve("magic_item", name)
        if not mid:
            continue
        for row in abilities_q.item_ability_sets(access, mid):
            out.setdefault(row["ability_id"], []).append((row["mode"], row["score"]))
    return out


def _owner_ability_sets(sheet: dict, access) -> dict[str, list[tuple[str, int]]]:
    """Ability-set/floor grants from the character's always-on owners — species, feats, each class,
    and each subclass — keyed by full DB ability id, gated by class-entry level.

    This is an independently rule-grounded owner set (following the saving-throws owner-gathering
    pattern), not a strict mirror of the deriver: the deriver applies grant_ability_set across a
    state-driven owner set, so coverage overlaps but is not identical. No grant_ability_set rows
    exist for non-item owners today, so this changes nothing now; it exists so a future non-item
    grant on one of these owners does not produce a false positive."""
    out: dict[str, list[tuple[str, int]]] = {}
    core = sheet.get("core", {}) or {}
    if not isinstance(core, dict):
        return out
    ident = core.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    def _collect(owner_kind: str, owner_id, at_level=None) -> None:
        if owner_id is None:
            return
        for row in abilities_q.granted_ability_sets(access, owner_kind, owner_id, at_level):
            out.setdefault(row["ability_id"], []).append((row["mode"], row["score"]))

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
    return out


def _check_effective_abilities(sheet: dict, access, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_abilities = core.get("abilities", {}) or {}
    effective = mod.get("effective_abilities", {}) or {}
    mod_abilities = mod.get("abilities", {}) or {}
    if not isinstance(effective, dict):
        return

    # Union ability-set grants from attuned items AND the always-on owners (species/feats/classes/
    # subclasses) — an independently rule-grounded owner set (the deriver accumulates across a
    # state-driven owner set; coverage overlaps but is not a strict mirror).
    ability_sets: dict[str, list[tuple[str, int]]] = {}
    for source in (_item_ability_sets(sheet, access), _owner_ability_sets(sheet, access)):
        for key, entries in source.items():
            ability_sets.setdefault(key, []).extend(entries)

    for aid, score in effective.items():
        if not _int(score):
            continue
        core_data = core_abilities.get(aid, {}) or {}
        if not isinstance(core_data, dict):
            core_data = {}
        reduction = mod_abilities.get(aid, {}).get("reduction", 0)
        if not _int(reduction):
            reduction = 0
        final = core_data.get("final", 10)
        if not _int(final):
            final = 10
        expected = final - reduction

        # `aid` is a MODIFIER short code; grant_ability_set.ability_id is the full DB id, so
        # normalise before matching item grants to this ability.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
        floor_score = None
        override_score = None
        for mode, s in ability_sets.get(full_aid, []):
            if not _int(s):
                continue
            if mode == "set":
                if override_score is None or s > override_score:
                    override_score = s
            else:  # floor: a minimum the score is raised to
                if floor_score is None or s > floor_score:
                    floor_score = s
        if floor_score is not None:
            expected = max(expected, floor_score)
        if override_score is not None:  # 'set' is a true override — it wins over base and floor
            expected = override_score

        if score != expected:
            v.append(Violation(DOMAIN, "effective-ability-mismatch", "illegal",
                               f"{aid}: effective {score} != expected {expected}",
                               f"effective_abilities.{aid}"))


# ── defenses ─────────────────────────────────────────────────────────────────


def _check_defenses(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    perm = core.get("permanent_defenses", {}) or {}
    eff = mod.get("effective_defenses", {}) or {}
    if not isinstance(perm, dict) or not isinstance(eff, dict):
        return

    for key in ("resistances", "immunities", "condition_immunities", "save_advantages"):
        core_set = set(perm.get(key, []) or [])
        mod_list = eff.get(key, []) or []
        if not isinstance(mod_list, list):
            continue
        missing = core_set - set(mod_list)
        for m in missing:
            label = key[:-1] if key.endswith("s") else key
            v.append(Violation(DOMAIN, "defense-subset-violation", "illegal",
                               f"missing core {label}: {m!r}", f"effective_defenses.{key}"))

    # condition_advantages are objects {condition, effect}; the MODIFIER must retain
    # every CORE condition advantage (compared by condition id).
    core_ca = perm.get("condition_advantages", []) or []
    mod_ca = eff.get("condition_advantages", []) or []
    if isinstance(core_ca, list) and isinstance(mod_ca, list):
        core_ca_conds = {e.get("condition") for e in core_ca
                         if isinstance(e, dict) and e.get("condition")}
        mod_ca_conds = {e.get("condition") for e in mod_ca
                        if isinstance(e, dict) and e.get("condition")}
        for c in core_ca_conds - mod_ca_conds:
            v.append(Violation(DOMAIN, "defense-subset-violation", "illegal",
                               f"missing core condition_advantage: {c!r}",
                               "effective_defenses.condition_advantages"))


def _check_state_defenses(sheet: dict, access, v: list[Violation]) -> None:
    """For each active character_state, gather the state's owner's condition-gated
    resistance grants from the DB and assert each damage type appears in
    effective_defenses.resistances. Grounded in the DB, not the deriver's output."""
    mod = sheet.get("modifier", {})
    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        return
    eff = mod.get("effective_defenses", {}) or {}
    if not isinstance(eff, dict):
        return
    res = eff.get("resistances", []) or []
    resistances = set(res) if isinstance(res, list) else set()

    for st in states:
        if not isinstance(st, dict):
            continue
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if owner_id is None:
            continue
        for row in defenses_q.state_resistance_grants(access, owner_kind, owner_id):
            dt = row["damage_type_id"]
            if dt and dt not in resistances:
                v.append(Violation(DOMAIN, "state-resistance-missing", "incomplete",
                                   f"active state {st.get('state')!r} grants resistance to {dt}, "
                                   f"not on effective_defenses",
                                   "effective_defenses.resistances"))


def _check_size(sheet: dict, access, v: list[Violation]) -> None:
    """Independently compute the expected effective_size from CORE.identity.size plus
    active-state size effects (relative steps and set-from-creature transformations),
    then compare to mod.effective_size."""
    core = sheet.get("core", {}) or {}
    mod = sheet.get("modifier", {}) or {}
    actual = mod.get("effective_size")
    if not isinstance(actual, str) or not actual:
        return
    ident = core.get("identity", {}) or {}
    base = ident.get("size", "medium") if isinstance(ident, dict) else "medium"

    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        states = []

    steps = 0
    set_candidates: list[str] = []
    for st in states:
        if not isinstance(st, dict):
            continue
        # Mirror the deriver's structural gate: a state contributes an effect only
        # when its source resolves to a grant owner.
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if owner_id is None:
            continue
        detail = st.get("detail")
        detail = detail if isinstance(detail, dict) else {}
        into = detail.get("into")
        if into:
            sz = size_q.creature_size(access, into)
            if sz:
                set_candidates.append(sz)
            continue
        variant = detail.get("effect")
        for row in size_q.size_grants(access, owner_kind, owner_id):
            if row["mode"] == "step":
                if variant is None or row["variant"] == variant:
                    steps += row["step"] or 0
            elif row["mode"] == "set" and row["size_id"]:
                set_candidates.append(row["size_id"])

    expected = base
    if set_candidates:
        expected = max(set_candidates, key=lambda s: size_q.size_ordinal(access, s) or 0)
    elif steps:
        base_ord = size_q.size_ordinal(access, base)
        if base_ord is not None:
            lo, hi = size_q.size_ordinal_bounds(access)
            target = max(lo, min(hi, base_ord + steps))
            resolved = size_q.size_by_ordinal(access, target)
            if resolved:
                expected = resolved

    if actual != expected:
        v.append(Violation(DOMAIN, "size-mismatch", "illegal",
                           f"effective_size {actual!r} != expected {expected!r}",
                           "effective_size"))


# ── passive scores ───────────────────────────────────────────────────────────


def _check_passives(sheet: dict, v: list[Violation]) -> None:
    mod = sheet.get("modifier", {})
    skills = mod.get("skills", {}) or {}
    passives = mod.get("passive_scores", {}) or {}
    if not isinstance(passives, dict):
        return

    for sid, score in passives.items():
        if not _int(score):
            continue
        skill_data = skills.get(sid, {}) or {}
        if not isinstance(skill_data, dict):
            continue
        expected = 10 + skill_data.get("modifier", 0)
        if score != expected:
            v.append(Violation(DOMAIN, "passive-score-mismatch", "illegal",
                               f"{sid}: passive {score} != expected {expected}",
                               f"passive_scores.{sid}"))


# ── features & feats presence ────────────────────────────────────────────────


def _check_features(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_feats = core.get("features", []) or []
    mod_feats = mod.get("features", []) or []
    if not isinstance(mod_feats, list):
        return
    core_names = set()
    for f in core_feats:
        if isinstance(f, dict):
            core_names.add(f.get("name", ""))
    mod_names = set()
    for f in mod_feats:
        if isinstance(f, dict):
            mod_names.add(f.get("name", ""))
    missing = core_names - mod_names
    for m in missing:
        v.append(Violation(DOMAIN, "feature-missing", "illegal",
                           f"CORE feature {m!r} not in MODIFIER", "features"))


def _check_feats(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_feats_list = core.get("feats", []) or []
    mod_feats_list = mod.get("feats", []) or []
    if not isinstance(mod_feats_list, list):
        return
    core_names = set()
    for f in core_feats_list:
        if isinstance(f, str):
            core_names.add(f)
        elif isinstance(f, dict):
            core_names.add(f.get("name", ""))
    mod_names = set()
    for f in mod_feats_list:
        if isinstance(f, dict):
            mod_names.add(f.get("name", ""))
    missing = core_names - mod_names
    for m in missing:
        v.append(Violation(DOMAIN, "feat-missing", "illegal",
                           f"CORE feat {m!r} not in MODIFIER", "feats"))


# ── prepared spells ──────────────────────────────────────────────────────────


def _check_prepared_spells(sheet: dict, access, v: list[Violation]) -> None:
    mod = sheet.get("modifier", {})
    grimoire = sheet.get("grimoire", {}) or {}
    prepared = mod.get("prepared_spells", []) or []
    if not isinstance(prepared, list) or not prepared:
        return

    grimoire_spells = grimoire.get("spells", []) or []
    valid_keys = set()
    for s in grimoire_spells:
        if isinstance(s, dict):
            name = s.get("name", "")
            source = s.get("source", "")
            if name:
                valid_keys.add(f"{name}|{source}")

    for entry in prepared:
        if not isinstance(entry, str):
            continue
        if entry not in valid_keys:
            v.append(Violation(DOMAIN, "prepared-spells-invalid", "illegal",
                               f"prepared spell {entry!r} not found in GRIMOIRE",
                               "prepared_spells"))


# ── state compatibility ──────────────────────────────────────────────────────


def _check_states(sheet: dict, access, v: list[Violation]) -> None:
    mod = sheet.get("modifier", {})
    states = mod.get("character_states", []) or []
    if not isinstance(states, list) or len(states) < 2:
        return

    active = set()
    for s in states:
        if isinstance(s, dict):
            state_id = s.get("state", "")
            if state_id:
                active.add(state_id)

    for sid in active:
        blocking = blocked_states(access.db, sid)
        conflicted = blocking & active
        for c in conflicted:
            v.append(Violation(DOMAIN, "state-incompatible", "illegal",
                               f"{sid!r} is incompatible with {c!r}",
                               "character_states"))


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    modifier = sheet.get("modifier")
    if modifier is None or not isinstance(modifier, dict):
        return v

    _check_ac(sheet, v)
    _check_ac_bonus_dedup(sheet, v)
    _check_saves(sheet, access, v)
    _check_skills(sheet, v)
    _check_attacks(sheet, access, v)
    _check_attack_damage(sheet, access, v)
    _check_effective_abilities(sheet, access, v)
    _check_defenses(sheet, v)
    _check_state_defenses(sheet, access, v)
    _check_size(sheet, access, v)
    _check_passives(sheet, v)
    _check_features(sheet, v)
    _check_feats(sheet, v)
    _check_prepared_spells(sheet, access, v)
    _check_states(sheet, access, v)

    return v
