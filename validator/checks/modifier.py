"""MODIFIER domain (modifier-sheet:1 shape): validates a modifier sheet against DB facts +
CORE/INVENTORY/GRIMOIRE inputs. 11 checks covering AC, saves, skills, effective abilities,
passives, defenses, features, feats, state compatibility, prepared spells, and stacking-rule
enforcement. NOT in ALL_CHECKS — modifier:1-specific."""
from access.validator import abilities as abilities_q
from access.validator.state_compatibility import blocked_states
from validator.report import Violation

DOMAIN = "modifier"


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


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


# ── effective abilities ──────────────────────────────────────────────────────


def _check_effective_abilities(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_abilities = core.get("abilities", {}) or {}
    effective = mod.get("effective_abilities", {}) or {}
    mod_abilities = mod.get("abilities", {}) or {}
    if not isinstance(effective, dict):
        return

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
        minimum = final - reduction
        if score < minimum:
            v.append(Violation(DOMAIN, "effective-ability-mismatch", "illegal",
                               f"{aid}: effective {score} < minimum {minimum} "
                               f"(final {final} - reduction {reduction})",
                               f"effective_abilities.{aid}"))


# ── defenses ─────────────────────────────────────────────────────────────────


def _check_defenses(sheet: dict, v: list[Violation]) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    perm = core.get("permanent_defenses", {}) or {}
    eff = mod.get("effective_defenses", {}) or {}
    if not isinstance(perm, dict) or not isinstance(eff, dict):
        return

    for key in ("resistances", "immunities", "condition_immunities"):
        core_set = set(perm.get(key, []) or [])
        mod_list = eff.get(key, []) or []
        if not isinstance(mod_list, list):
            continue
        missing = core_set - set(mod_list)
        for m in missing:
            v.append(Violation(DOMAIN, "defense-subset-violation", "illegal",
                               f"missing core {key[:-1]}: {m!r}", f"effective_defenses.{key}"))


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
    _check_effective_abilities(sheet, v)
    _check_defenses(sheet, v)
    _check_passives(sheet, v)
    _check_features(sheet, v)
    _check_feats(sheet, v)
    _check_prepared_spells(sheet, access, v)
    _check_states(sheet, access, v)

    return v
