"""MODIFIER domain (modifier-sheet:1 shape): validates a modifier sheet against DB facts +
CORE/INVENTORY/GRIMOIRE inputs. Checks cover AC, saves, skills, attacks, effective abilities,
passives, defenses, features, feats, state compatibility, prepared spells, and stacking-rule
enforcement. NOT in ALL_CHECKS — modifier:1-specific."""
from access.constants import CON_ABBREV
from access.validator import abilities as abilities_q
from access.validator import attacks as attacks_q
from access.validator import conditions as conditions_q
from access.validator import creature as creature_q
from access.validator import defenses as defenses_q
from access.validator import features as features_q
from access.validator import inventory as inventory_q
from access.validator import movement as movement_q
from access.validator import size as size_q
from access.validator import skills as skills_q
from access.validator import spellcasting as spellcasting_q
from access.validator import vitals as vitals_q
from access.validator.state_compatibility import blocked_states
from validator.report import Violation

DOMAIN = "modifier"

# Self-transform (T60): the character temporarily BECOMES a creature. 'physical' (physical-form)
# replaces the physical abilities only (mental abilities retained); 'full' replaces all six.
# The mental set is a rule constant (the split is fixed by the ruleset). Re-derived here so the
# check stays independent of the deriver.
TRANSFORM_PHYSICAL = "physical"
TRANSFORM_FULL = "full"
_TRANSFORM_KINDS = (TRANSFORM_PHYSICAL, TRANSFORM_FULL)
_MENTAL_ABILITY_IDS = frozenset({"intelligence", "wisdom", "charisma"})


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


def _check_saves(sheet: dict, access, v: list[Violation], transform: dict | None = None) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_saves = core.get("saving_throws", {}) or {}
    pb = core.get("proficiency_bonus", 0)
    core_abilities = core.get("abilities", {}) or {}
    mod_saves = mod.get("saving_throws", {}) or {}
    mod_abilities = mod.get("abilities", {}) or {}
    if not isinstance(core_saves, dict) or not isinstance(mod_saves, dict):
        return

    # Under a FULL transform saves are the FORM's stat-block saves — the form's ability modifier
    # plus the form's own proficiency bonus where the form is proficient (T63), NO character
    # proficiency/PB and no item bonus (gear melds into the form). A PHYSICAL transform keeps the
    # character's own proficiencies/PB on the (partly replaced) ability modifiers, then takes the
    # HIGHER OF the character's own save and the form's — gaining the form's proficiency (T65).
    full_transform = bool(transform and transform["kind"] == TRANSFORM_FULL)
    item_all_bonus, item_per_ability = (0, {}) if full_transform else _item_save_bonuses(sheet, access)
    form_saves = _form_save_mods(access, transform["creature_id"]) if transform else {}
    form_save_prof = _form_save_proficiencies(access, transform["creature_id"]) if transform else set()

    for aid, save_obj in mod_saves.items():
        if not isinstance(save_obj, dict):
            continue
        actual = save_obj.get("modifier")
        if not _int(actual):
            continue

        # `aid` is the MODIFIER save key (a short code); per-ability item bonuses and form saves are
        # keyed by the grant/creature's full DB ability id, so normalise before matching.
        full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid

        if full_transform:
            ab_mod = (mod_abilities.get(aid, {}) or {}).get("modifier", 0)
            expected = form_saves.get(full_aid, ab_mod)
            if actual != expected:
                v.append(Violation(DOMAIN, "save-modifier-mismatch", "illegal",
                                   f"{aid}: modifier {actual} != expected {expected}",
                                   f"saving_throws.{aid}.modifier"))
            continue

        core_save = core_saves.get(aid)
        if isinstance(core_save, dict):
            proficient = core_save.get("proficient", False)
        else:
            proficient = bool(core_save)
        # PHYSICAL transform: gain the form's save proficiencies (applied with the character's OWN PB).
        if transform and full_aid in form_save_prof:
            proficient = True
        ab_data = mod_abilities.get(aid, {}) or {}
        ab_mod = ab_data.get("modifier", 0)

        expected = ab_mod
        if proficient and _int(pb):
            expected += pb
        expected += item_all_bonus + item_per_ability.get(full_aid, 0)
        if transform:  # PHYSICAL transform: higher of the character's own save and the form's block
            expected = max(expected, form_saves.get(full_aid, expected))

        if actual != expected:
            v.append(Violation(DOMAIN, "save-modifier-mismatch", "illegal",
                               f"{aid}: modifier {actual} != expected {expected}",
                               f"saving_throws.{aid}.modifier"))


# ── skills ───────────────────────────────────────────────────────────────────


def _check_skills(sheet: dict, access, v: list[Violation], transform: dict | None = None) -> None:
    core = sheet.get("core", {})
    mod = sheet.get("modifier", {})
    core_skills = core.get("skills", {}) or {}
    pb = core.get("proficiency_bonus", 0)
    mod_abilities = mod.get("abilities", {}) or {}
    mod_skills = mod.get("skills", {}) or {}
    if not isinstance(mod_skills, dict):
        return

    # Under a FULL transform skills are the FORM's stat-block skills — the form's skill bonus where
    # the form has that skill, else the form's ability modifier, with NO character proficiency/PB. A
    # PHYSICAL transform keeps the character's own proficiencies/PB, then takes the HIGHER OF the
    # character's own skill and the form's — gaining the form's skill proficiency (T65).
    full_transform = bool(transform and transform["kind"] == TRANSFORM_FULL)
    form_skills = _form_skill_mods(access, transform["creature_id"]) if transform else {}

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
        # `sid` is the sheet's skill key (a display name); the form's skills are keyed by the DB
        # skill id, so resolve before looking up a form skill bonus / proficiency.
        form_sid = access.resolve("skill", sid) or sid if transform else None
        form_only = bool(transform) and sid not in core_skills and form_sid in form_skills
        if form_only:
            # A skill the form is proficient in that the base character does not list (T108) — the
            # gained skill takes the form's stat-block bonus.
            expected = form_skills[form_sid]
        elif full_transform:
            expected = form_skills.get(form_sid, ab_mod)
        else:
            expected = ab_mod
            if _int(pb):
                # PHYSICAL transform: gain the form's skill proficiency (own PB) in addition to own.
                prof = core_skill.get("proficient") or (bool(transform) and form_sid in form_skills)
                if core_skill.get("expertise"):
                    expected += pb * 2
                elif prof:
                    expected += pb
            if transform:  # PHYSICAL transform: higher of the character's own skill and the form's
                expected = max(expected, form_skills.get(form_sid, expected))

        if actual != expected:
            v.append(Violation(DOMAIN, "skill-modifier-mismatch", "illegal",
                               f"{sid}: modifier {actual} != expected {expected}",
                               f"skills.{sid}.modifier"))

    # Form-only skills (T108): each skill the form is proficient in that the base character does not
    # list must be emitted on the transformed sheet — re-derived here independently of the deriver.
    if transform and form_skills:
        core_ids = {access.resolve("skill", k) or k for k in core_skills}
        present_ids = {access.resolve("skill", k) or k for k in mod_skills}
        for form_sid in form_skills:
            if form_sid in core_ids or form_sid in present_ids:
                continue
            name = skills_q.skill_name(access, form_sid) or form_sid
            v.append(Violation(DOMAIN, "form-skill-missing", "incomplete",
                               f"gained form skill {name} not emitted",
                               f"skills.{name}"))


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


def _spellcasting_ability_id(access, core: dict, owner_kind: str, owner_id: str) -> str | None:
    """The character's spellcasting-ability id for a granted attack, re-derived here independently of
    the deriver: walk CORE.identity.classes, keep each caster class's spellcasting ability
    (``class_primary_ability``), and — when the granting owner is a spell — prefer the caster class
    whose spell list carries that spell (the ability "you cast it with"); else the first caster."""
    ident = core.get("identity", {}) or {}
    classes = ident.get("classes", []) if isinstance(ident, dict) else []
    caster_abilities: list[tuple[str, str]] = []
    if isinstance(classes, list):
        for c in classes:
            if not isinstance(c, dict):
                continue
            cid = access.resolve("class", c.get("class"))
            if not cid:
                continue
            ab = spellcasting_q.class_spellcasting_ability(access, cid)
            if ab:
                caster_abilities.append((cid, ab))
    if not caster_abilities:
        return None
    if owner_kind == "spell":
        for cid, ab in caster_abilities:
            if owner_id and spellcasting_q.spell_on_class_list(access, owner_id, cid):
                return ab
    return caster_abilities[0][1]


def _granted_attack_ability_mod(access, core: dict, mod_abilities: dict, grant,
                                owner_kind: str, owner_id: str) -> int:
    """The ability modifier a granted attack (grant_attack row) adds to its bonus and damage,
    re-derived here independently of the deriver, by ability_mode: 'spellcasting' → the character's
    spellcasting-ability modifier (resolved against the granting owner); 'strength' → the Strength
    modifier (an unarmed/natural attack that uses Strength); 'finesse' → the better of
    Strength/Dexterity (matching the finesse rule); anything else → 0 (the fallback)."""
    mode = grant["ability_mode"]
    if mode == "spellcasting":
        ability_id = _spellcasting_ability_id(access, core, owner_kind, owner_id)
        return _mod_for_ability(access, mod_abilities, ability_id) if ability_id else 0
    if mode == "strength":
        return _mod_for_ability(access, mod_abilities, "strength")
    if mode == "finesse":
        return max(_mod_for_ability(access, mod_abilities, "strength"),
                   _mod_for_ability(access, mod_abilities, "dexterity"))
    return 0


def _assert_granted_attack(grant, ab_mod: int, pb, by_name: dict, v: list[Violation],
                           context: str = "") -> None:
    """Assert one effect-granted attack appears on the MODIFIER with the expected bonus, damage and
    type. The attack bonus adds the character's PB (the growth reshapes the always-proficient unarmed
    strike) and the damage adds the resolved ability modifier; the die term and damage type come from
    the DB row. A missing attack is flagged incomplete; a present-but-wrong one is flagged illegal.
    Shared by the state-owner, item-owner and permanent-owner passes."""
    dc, df = grant["die_count"], grant["die_faces"]
    if not (_int(dc) and _int(df)):
        return
    expected_bonus = ab_mod + (pb if _int(pb) else 0)
    expected_damage = f"{dc}d{df}"
    if ab_mod > 0:
        expected_damage += f"+{ab_mod}"
    elif ab_mod < 0:
        expected_damage += str(ab_mod)
    name = grant["name"]

    atk = by_name.get(name)
    if atk is None:
        v.append(Violation(DOMAIN, "granted-attack-missing", "incomplete",
                           f"effect-granted attack {name!r}{context} not in attacks", "attacks"))
        return
    if atk.get("attack_bonus") != expected_bonus:
        v.append(Violation(DOMAIN, "granted-attack-bonus-mismatch", "illegal",
                           f"{name}: attack bonus {atk.get('attack_bonus')} != expected "
                           f"{expected_bonus}", "attacks"))
    if atk.get("damage") != expected_damage:
        v.append(Violation(DOMAIN, "granted-attack-damage-mismatch", "illegal",
                           f"{name}: damage {atk.get('damage')!r} != expected "
                           f"{expected_damage!r}", "attacks"))
    if grant["damage_type"] is not None and atk.get("damage_type") != grant["damage_type"]:
        v.append(Violation(DOMAIN, "granted-attack-type-mismatch", "illegal",
                           f"{name}: damage_type {atk.get('damage_type')!r} != expected "
                           f"{grant['damage_type']!r}", "attacks"))


def _permanent_owner_granted_attacks(sheet: dict, access) -> list[tuple[str, str, object]]:
    """Grant_attack rows from the character's always-on owners — species, feats, each class, and each
    subclass — gated by class-entry level, each tagged with its (owner_kind, owner_id). Mirrors
    ``_owner_ability_sets``: an independently rule-grounded owner set, inert until a non-state,
    non-item grant_attack lands on one of these owners (none exist in the reference dataset today)."""
    out: list[tuple[str, str, object]] = []
    core = sheet.get("core", {}) or {}
    if not isinstance(core, dict):
        return out
    ident = core.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    def _collect(owner_kind: str, owner_id, at_level=None) -> None:
        if owner_id is None:
            return
        for grant in attacks_q.attack_grants(access, owner_kind, owner_id, at_level):
            out.append((owner_kind, owner_id, grant))

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


def _check_granted_attacks(sheet: dict, access, v: list[Violation]) -> None:
    """Independently re-derive each effect-granted attack from grant_attack (never from the deriver's
    attacks[]) and assert it appears on the MODIFIER with the correct bonus, damage and type.

    Three owner sources contribute grants: active states (their resolved owner), the character's
    always-on permanent owners (species/feats/classes/subclasses), and equipped/attuned magic items.
    The ability_mode ('spellcasting'/'strength'/'finesse') is re-derived here; all three passes share
    the same expected-value assertion."""
    core = sheet.get("core", {}) or {}
    mod = sheet.get("modifier", {}) or {}
    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        states = []
    attacks = mod.get("attacks", []) or []
    if not isinstance(attacks, list):
        attacks = []
    by_name = {a.get("name"): a for a in attacks if isinstance(a, dict) and a.get("name")}
    pb = core.get("proficiency_bonus", 0)
    mod_abilities = mod.get("abilities", {}) or {}

    for st in states:
        if not isinstance(st, dict):
            continue
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if owner_id is None:
            continue
        for grant in attacks_q.attack_grants(access, owner_kind, owner_id):
            ab_mod = _granted_attack_ability_mod(access, core, mod_abilities, grant,
                                                 owner_kind, owner_id)
            _assert_granted_attack(grant, ab_mod, pb, by_name, v,
                                   context=f" (state {st.get('state')!r})")

    # Permanent-owner pass: always-on granted attacks from species/feats/classes/subclasses.
    for owner_kind, owner_id, grant in _permanent_owner_granted_attacks(sheet, access):
        ab_mod = _granted_attack_ability_mod(access, core, mod_abilities, grant,
                                             owner_kind, owner_id)
        _assert_granted_attack(grant, ab_mod, pb, by_name, v, context=f" ({owner_kind} owner)")


def _item_rider_active(sheet: dict, access, weapon_name: str, magic_item_id: str) -> bool:
    """True if the equipped magic weapon named ``weapon_name`` is active for its extra-damage rider.

    Mirrors the deriver's activity gate: an item that requires attunement is active only when it
    carries an attuned item_state (matched via inventory_ref → equipped id); an item that does not
    require attunement is active while equipped. Grounded in the sheet + DB, not the deriver."""
    inventory = sheet.get("inventory", {}) or {}
    if not isinstance(inventory, dict):
        return False
    equipped = inventory.get("equipped", {}) or {}
    if not isinstance(equipped, dict):
        return False
    item_id = None
    for slot_item in equipped.values():
        if isinstance(slot_item, dict) and slot_item.get("name") == weapon_name:
            item_id = slot_item.get("id")
            break
    if item_id is None:
        return False  # not an equipped weapon → the deriver never folded a rider into it
    if not inventory_q.requires_attunement(access, magic_item_id):
        return True
    mod = sheet.get("modifier", {}) or {}
    item_states = mod.get("item_states", []) or []
    if not isinstance(item_states, list):
        return False
    for ist in item_states:
        if (isinstance(ist, dict) and ist.get("attuned")
                and ist.get("inventory_ref") == item_id):
            return True
    return False


def _check_attack_damage(sheet: dict, access, v: list[Violation]) -> None:
    """Independently re-derive extra-damage riders from the DB and assert each appears in the
    relevant attacks' ``damage`` string. Grounded in the DB, not the deriver's output. Two rider
    sources are checked:

    * state-gated riders (active state → owner → condition-gated extra_damage grant) apply to
      EVERY weapon attack;
    * an item-owned rider (a weapon-backed magic item owning exactly one extra_damage grant, active
      per attunement/equip) applies only to THAT weapon's own attack.
    """
    mod = sheet.get("modifier", {})
    attacks = mod.get("attacks", []) or []
    states = mod.get("character_states", []) or []
    if not isinstance(attacks, list) or not attacks:
        return
    if not isinstance(states, list):
        states = []

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

    # The deriver folds riders only into WEAPON attacks (entries produced from an equipped
    # weapon). Scope both assertions the same way — resolve each attack's name to a weapon and
    # skip anything that isn't one (a spell/unarmed entry the deriver never folded a rider into)
    # so a non-weapon attack can't false-positive rider-missing.
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

        # state riders apply to every weapon attack
        for term in terms:
            if term not in damage:
                v.append(Violation(DOMAIN, "attack-damage-rider-missing", "incomplete",
                                   f"{name}: expected extra-damage rider {term} from "
                                   f"active state, not in damage {damage!r}", "attacks"))

        # item-owned rider: only THIS weapon's own single-row, weapon-backed magic item. A negative
        # rider term is legitimate (a subtractive rider) and must appear verbatim, not be flagged.
        mid = access.resolve("magic_item", name)
        if mid is None:
            continue
        rows = inventory_q.extra_damage_grants(access, "magic_item", mid)
        # Re-derive the disambiguation independently (F05-T57): among the item's extra-damage rows,
        # the single UNGATED row is the always-on rider; condition_kind-gated rows are state-scoped
        # (the state path owns them). Assert only that one ungated rider — more than one is ambiguous
        # (folds nothing) and a lone gated row belongs to the state path, so neither is asserted here.
        ungated = [r for r in rows if r["condition_kind"] is None]
        if len(ungated) != 1:
            continue
        dc, df = ungated[0]["die_count"], ungated[0]["die_faces"]
        if not (_int(dc) and _int(df) and dc != 0):
            continue
        if not _item_rider_active(sheet, access, name, mid):
            continue
        term = f"{'+' if dc > 0 else '-'}{abs(dc)}d{df}"
        if term not in damage:
            v.append(Violation(DOMAIN, "item-attack-damage-rider-missing", "incomplete",
                               f"{name}: expected item extra-damage rider {term}, "
                               f"not in damage {damage!r}", "attacks"))


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


# ── hit points (effective-CON max-HP recompute) ──────────────────────────────


def _total_level(core: dict) -> int:
    """Sum of the character's per-class levels from CORE.identity.classes."""
    ident = core.get("identity", {}) or {}
    classes = ident.get("classes", []) if isinstance(ident, dict) else []
    total = 0
    if isinstance(classes, list):
        for c in classes:
            if isinstance(c, dict) and _int(c.get("level")):
                total += c["level"]
    return total


def _con_hp_delta(sheet: dict, access, total_level: int) -> int:
    """Independently re-derived HP delta from the effective-CON change, ``(eff_con_mod −
    core_con_mod) × total_level``.

    ``core_con_mod`` is read from CORE.abilities (the ability whose key resolves to the
    constitution id). The effective CON is CORE-final adjusted by ability-set/floor grants from the
    SAME sources the effective-ability check uses (attuned items + always-on owners), applied to the
    constitution id. Grounded in the DB + CORE, never the deriver's ``effective_abilities``."""
    con_id = abilities_q.ability_id(access, CON_ABBREV)
    if con_id is None:
        return 0
    core = sheet.get("core", {}) or {}
    core_abilities = core.get("abilities", {}) or {}
    if not isinstance(core_abilities, dict):
        return 0
    core_con_final = None
    for k, entry in core_abilities.items():
        if abilities_q.ability_id(access, k) != con_id:
            continue
        if isinstance(entry, dict):
            f = entry.get("final")
            if _int(f):
                core_con_final = f
        break
    if not _int(core_con_final):
        return 0
    core_con_mod = (core_con_final - 10) // 2

    ability_sets: dict[str, list[tuple[str, int]]] = {}
    for source in (_item_ability_sets(sheet, access), _owner_ability_sets(sheet, access)):
        for key, entries in source.items():
            ability_sets.setdefault(key, []).extend(entries)

    eff_con = core_con_final
    floor_score = None
    override_score = None
    for mode, s in ability_sets.get(con_id, []):
        if not _int(s):
            continue
        if mode == "set":
            if override_score is None or s > override_score:
                override_score = s
        else:  # floor: a minimum the score is raised to
            if floor_score is None or s > floor_score:
                floor_score = s
    if floor_score is not None:
        eff_con = max(eff_con, floor_score)
    if override_score is not None:  # 'set' is a true override — wins over base and floor
        eff_con = override_score
    eff_con_mod = (eff_con - 10) // 2

    return (eff_con_mod - core_con_mod) * total_level


def _state_hp(sheet: dict, access) -> tuple[int, int]:
    """Total (boost, reduction) from grant_hp rows owned by ACTIVE character_states' owners.

    Mirrors the deriver's state-only HP accumulation and its gate + sign rule: only a state's owner
    contributes (an always-on owner's grant_hp never does), a grant applies when ungated or its
    condition_kind matches the state's id, and a NEGATIVE amount is a drain/curse into max_reduction
    while a positive one raises max_boost (F05-T58). Combined with the CON-delta to reconstruct
    max_boost / max_reduction — omitting either would false-positive on a legitimate state effect."""
    mod = sheet.get("modifier", {}) or {}
    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        return 0, 0
    boost = 0
    reduction = 0
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
        for row in vitals_q.state_hp_grants(access, owner_kind, owner_id):
            gate = row["condition_kind"]
            if gate is not None and gate != state_id:
                continue
            # A VARIABLE drain (dice, no fixed amount) is a live-play reduction, bounds-checked
            # separately (T112) — it is NOT part of the exact fixed boost/reduction expectation.
            if row["die_count"] is not None:
                continue
            amount = (row["flat"] or 0) + (row["per_level"] or 0)
            if amount >= 0:
                boost += amount
            else:
                reduction += -amount
    return boost, reduction


def _active_variable_drains(sheet: dict, access) -> list[tuple[int, int]]:
    """The (min, max) reduction bounds of each active VARIABLE state-gated max-HP drain, re-derived
    from the drain's dice (die_count .. die_count*die_faces). A variable drain's magnitude is the
    dice-rolled damage taken — a live-play value the check bounds-checks rather than a fixed number
    (F05-T112)."""
    mod = sheet.get("modifier", {}) or {}
    states = mod.get("character_states", []) or []
    bounds: list[tuple[int, int]] = []
    if not isinstance(states, list):
        return bounds
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
        for row in vitals_q.state_hp_grants(access, owner_kind, owner_id):
            gate = row["condition_kind"]
            if gate is not None and gate != state_id:
                continue
            dc, df = row["die_count"], row["die_faces"]
            if _int(dc) and _int(df):
                bounds.append((dc, dc * df))
    return bounds


def _check_hp(sheet: dict, access, v: list[Violation], transform: dict | None = None) -> None:
    """Assert MODIFIER.hit_points.max_boost / max_reduction reflect the effective-CON max-HP
    recompute (as a delta on the state HP boost). The modifier sheet has no absolute max — the
    effective max is CORE.hit_points.max + max_boost − max_reduction — so the recompute is expressed
    as a delta: a positive CON delta raises max_boost, a negative one raises max_reduction.

    Under a self-transform the character retains their OWN Hit Points, so the form's CON does NOT
    recompute max HP (the form's HP is a separate live-play Temporary-HP pool, not derived) — the
    expected CON delta is 0 (T60 fork 2)."""
    core = sheet.get("core", {}) or {}
    mod = sheet.get("modifier", {}) or {}
    if not isinstance(core, dict) or not isinstance(mod, dict):
        return
    hp = mod.get("hit_points")
    if not isinstance(hp, dict):
        return
    actual_boost = hp.get("max_boost")
    actual_reduction = hp.get("max_reduction")
    if not _int(actual_boost) or not _int(actual_reduction):
        return

    total_level = _total_level(core)
    hp_delta = 0 if transform else _con_hp_delta(sheet, access, total_level)
    state_boost, state_reduction = _state_hp(sheet, access)

    expected_boost = state_boost + max(0, hp_delta)
    expected_reduction = state_reduction + max(0, -hp_delta)

    if actual_boost != expected_boost:
        v.append(Violation(DOMAIN, "hp-max-boost-mismatch", "illegal",
                           f"max_boost {actual_boost} != expected {expected_boost}",
                           "hit_points.max_boost"))
    # A VARIABLE drain contributes a live-play (dice-rolled) reduction that is not a fixed derivable
    # magnitude, so the exact-equality reduction check is suspended when one is active — the drain is
    # bounds-checked in _check_hp_drain instead (F05-T112).
    if not _active_variable_drains(sheet, access) and actual_reduction != expected_reduction:
        v.append(Violation(DOMAIN, "hp-max-reduction-mismatch", "illegal",
                           f"max_reduction {actual_reduction} != expected {expected_reduction}",
                           "hit_points.max_reduction"))


def _check_hp_drain(sheet: dict, access, v: list[Violation], transform: dict | None = None) -> None:
    """Bounds-check the live-play max-HP reduction from any active VARIABLE state-gated drain. The
    reduction is the dice-rolled damage taken (an inherently variable, live-play amount), so rather
    than a fixed derived value the check enforces internal book-consistency: the drain portion of
    ``max_reduction`` must lie within the drain's dice bounds, and the reduction must not push the
    effective maximum HP below 1 (F05-T112).

    Under a self-transform the character keeps their OWN Hit Points, so the form's CON does NOT
    recompute max HP — the CON delta is 0 (T60 fork 2). The drain-base uses the SAME 0-CON-delta rule
    as ``_check_hp`` so the two HP paths agree; otherwise a miscounted CON base would shift the
    derived drain amount and spuriously flag an in-bounds live drain."""
    drains = _active_variable_drains(sheet, access)
    if not drains:
        return
    core = sheet.get("core", {}) or {}
    mod = sheet.get("modifier", {}) or {}
    hp = mod.get("hit_points")
    if not isinstance(core, dict) or not isinstance(hp, dict):
        return
    actual_reduction = hp.get("max_reduction")
    actual_boost = hp.get("max_boost")
    if not _int(actual_reduction) or not _int(actual_boost):
        return

    # The derivable (fixed) reduction is the base; the variable drains add a live-play amount on top.
    _, fixed_reduction = _state_hp(sheet, access)
    total_level = _total_level(core)
    hp_delta = 0 if transform else _con_hp_delta(sheet, access, total_level)
    base_reduction = fixed_reduction + max(0, -hp_delta)
    drain_amount = actual_reduction - base_reduction

    low = sum(dmin for dmin, _ in drains)
    high = sum(dmax for _, dmax in drains)
    if drain_amount < low or drain_amount > high:
        v.append(Violation(DOMAIN, "hp-drain-out-of-bounds", "illegal",
                           f"state-gated max-HP drain {drain_amount} outside the rolled-damage "
                           f"bounds [{low}, {high}]", "hit_points.max_reduction"))

    core_max = (core.get("hit_points", {}) or {}).get("max")
    if _int(core_max):
        effective_max = core_max + actual_boost - actual_reduction
        if effective_max < 1:
            v.append(Violation(DOMAIN, "hp-drain-below-floor", "illegal",
                               f"effective max HP {effective_max} < 1 — the drain cannot reduce the "
                               f"Hit Point maximum below 1", "hit_points.max_reduction"))


def _expected_form_pool(sheet: dict, access, transform: dict) -> int | None:
    """Independently re-derive the self-transform temporary form-HP pool from DB facts + CORE (T108):
    a FULL transform's pool is the form's own hit points; a PHYSICAL transform's pool is the level of
    the class whose feature grants the transform. Returns None when the pool cannot be derived."""
    if transform["kind"] == TRANSFORM_FULL:
        row = creature_q.creature_row(access, transform["creature_id"])
        return row["hp_average"] if row is not None and _int(row["hp_average"]) else None
    # PHYSICAL: the granting class's level, resolved from the transform's source class feature
    if transform.get("owner_kind") != "class_feature" or not transform.get("owner_id"):
        return None
    class_id = features_q.class_feature_class(access, transform["owner_id"])
    if not class_id:
        return None
    core = sheet.get("core", {}) or {}
    ident = core.get("identity", {}) or {}
    classes = ident.get("classes", []) if isinstance(ident, dict) else []
    if isinstance(classes, list):
        for c in classes:
            if not isinstance(c, dict) or not _int(c.get("level")):
                continue
            if access.resolve("class", c.get("class")) == class_id:
                return c["level"]
    return None


def _check_form_hp_pool(sheet: dict, access, v: list[Violation],
                        transform: dict | None = None) -> None:
    """Assert MODIFIER.hit_points.form_temp_pool matches the independently re-derived self-transform
    temporary form-HP pool. Only runs while a transform is active; a pool that cannot be derived
    (missing owner/class context) yields no assertion (T108)."""
    if not transform:
        return
    mod = sheet.get("modifier", {}) or {}
    hp = mod.get("hit_points")
    if not isinstance(hp, dict):
        return
    expected = _expected_form_pool(sheet, access, transform)
    if expected is None:
        return
    actual = hp.get("form_temp_pool")
    if actual is None:
        v.append(Violation(DOMAIN, "form-hp-pool-missing", "incomplete",
                           f"self-transform temporary HP pool {expected} not emitted",
                           "hit_points.form_temp_pool"))
    elif actual != expected:
        v.append(Violation(DOMAIN, "form-hp-pool-mismatch", "illegal",
                           f"form_temp_pool {actual} != expected {expected}",
                           "hit_points.form_temp_pool"))


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


def _per_level_coeff(modifier: str) -> int:
    """Parse a ``<coeff>_per_level`` modifier formula into its integer coefficient.
    Re-implemented here so the check stays independent of the deriver."""
    try:
        return int(str(modifier).split("_per_level", 1)[0])
    except (ValueError, TypeError):
        return 0


def _core_speed_view(sheet: dict) -> dict:
    """A CORE-shaped view of the MODIFIER sheet for the movement domain's shared speed walkers.

    Carries the CORE identity and feats plus the inventory's equipped/backpack items, annotating
    each item's attunement from the MODIFIER item_states. The shared item-grant walker then gates
    attunement-required items exactly as the deriver does: an attuned item (recorded in item_states)
    contributes its grants, while a non-attunement magic item contributes while equipped/carried."""
    core = sheet.get("core", {}) or {}
    if not isinstance(core, dict):
        core = {}
    inv = sheet.get("inventory", {}) or {}
    if not isinstance(inv, dict):
        inv = {}
    mod = sheet.get("modifier", {}) or {}
    item_states = mod.get("item_states", []) or []
    attuned_ids = {ist.get("inventory_ref") for ist in item_states
                   if isinstance(ist, dict) and ist.get("attuned")}

    def _annotate(item):
        if not isinstance(item, dict):
            return item
        if item.get("id") in attuned_ids:
            out = dict(item)
            out["attunement"] = {"attuned": True}
            return out
        return item

    equipped = inv.get("equipped", {})
    equipped_view = {}
    if isinstance(equipped, dict):
        for slot, it in equipped.items():
            equipped_view[slot] = _annotate(it)
    backpack = inv.get("backpack", [])
    backpack_view = [_annotate(it) for it in backpack] if isinstance(backpack, list) else []
    return {
        "identity": core.get("identity", {}) or {},
        "feats": core.get("feats", []) or [],
        "equipped": equipped_view,
        "backpack": backpack_view,
    }


def _base_effective_speeds(sheet: dict, access) -> dict:
    """Re-derive the character's effective speeds BEFORE any condition effect, independently from
    DB facts and the rule (never from the deriver): the species/lineage base walk, every
    non-condition owner speed grant (species, lineage, class, subclass, feat, magic items), the
    class movement bonus, and active non-condition state speed grants. Resolution reuses the
    movement domain's shared walkers/resolver so the base matches the fully-resolved pre-penalty
    speed the deriver subtracts the condition penalty from."""
    from validator.checks.movement import _resolve_speeds

    core = sheet.get("core", {}) or {}
    ident = core.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    core_view = _core_speed_view(sheet)

    spid = access.resolve("species", ident.get("species"))
    base_walk = movement_q.species_base_walk(access, spid) if spid else 0
    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            parent = movement_q.lineage_parent_species(access, lid)
            if parent and not base_walk:
                base_walk = movement_q.species_base_walk(access, parent) or base_walk
    if not _int(base_walk):
        base_walk = 0

    grants = movement_q.gather_owner_grants(access, core_view)
    class_bonuses = movement_q.gather_class_bonuses(access, core_view)

    # Active non-condition states (e.g. a speed-granting spell buff) are not walked by
    # gather_owner_grants (which covers always-on owners) — add their grants here.
    mod = sheet.get("modifier", {}) or {}
    for st in mod.get("character_states", []) or []:
        if not isinstance(st, dict):
            continue
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None or owner_kind == "condition":
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if not owner_id:
            continue
        for row in movement_q.speed_grants(access, owner_kind, owner_id):
            grants.append(dict(row))

    return _resolve_speeds(grants, base_walk, class_bonuses)


def _check_condition_effects(sheet: dict, access, v: list[Violation]) -> None:
    """Independently re-derive the sheet-derivable effects of every active condition
    from condition_effect (never from the deriver) and assert the MODIFIER reflects them:
    an absolute speed-zero, a per-level speed penalty, a per-level D20-test penalty,
    resistance to all damage, and condition/damage immunities."""
    mod = sheet.get("modifier", {}) or {}
    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        return

    speed_zero = False
    speed_penalty = 0
    d20_penalty = 0
    resistance_all = False
    cond_immunities: set = set()
    dmg_immunities: set = set()
    saw_condition = False

    for st in states:
        if not isinstance(st, dict):
            continue
        if _owner_kind_for_source_type(st.get("source_type", "")) != "condition":
            continue
        state_id = st.get("state")
        if not state_id:
            continue
        level = st.get("level")
        has_level = _int(level)
        cond_id = conditions_q.condition_id_for_state(access, state_id, has_level)
        if not cond_id:
            continue
        saw_condition = True
        lvl = level if has_level else 0
        for row in conditions_q.condition_effects(access, cond_id):
            kind = row["effect_kind"]
            m = row["modifier"]
            tk = row["target_kind"]
            tid = row["target_id"]
            if kind == "speed_set" and m == "set_0":
                speed_zero = True
            elif kind == "speed_penalty":
                speed_penalty += abs(_per_level_coeff(m)) * lvl
            elif kind == "d20_penalty":
                d20_penalty += abs(_per_level_coeff(m)) * lvl
            elif kind == "resistance" and m == "resistance_all":
                resistance_all = True
            elif kind == "immunity" and tk == "condition" and tid:
                cond_immunities.add(tid)
            elif kind == "immunity" and tk == "damage" and tid:
                dmg_immunities.add(tid)

    if not saw_condition:
        return

    actual_d20 = mod.get("d20_penalty", 0)
    if not _int(actual_d20):
        actual_d20 = 0
    if actual_d20 != d20_penalty:
        v.append(Violation(DOMAIN, "condition-d20-penalty-mismatch", "illegal",
                           f"expected d20_penalty {d20_penalty}, got {actual_d20}",
                           "d20_penalty"))

    eff = mod.get("effective_defenses", {}) or {}
    if isinstance(eff, dict):
        res = set(eff.get("resistances", []) or [])
        if resistance_all:
            missing = set(defenses_q.damage_type_ids(access)) - res
            if missing:
                v.append(Violation(DOMAIN, "condition-resistance-missing", "incomplete",
                                   "active condition grants resistance to all damage; "
                                   f"missing {sorted(missing)}",
                                   "effective_defenses.resistances"))
        ci = set(eff.get("condition_immunities", []) or [])
        for c in sorted(cond_immunities - ci):
            v.append(Violation(DOMAIN, "condition-immunity-missing", "incomplete",
                               f"active condition grants immunity to the {c!r} condition, "
                               "not on effective_defenses",
                               "effective_defenses.condition_immunities"))
        di = set(eff.get("immunities", []) or [])
        for d in sorted(dmg_immunities - di):
            v.append(Violation(DOMAIN, "condition-damage-immunity-missing", "incomplete",
                               f"active condition grants immunity to {d} damage, "
                               "not on effective_defenses",
                               "effective_defenses.immunities"))

    _check_condition_speed(sheet, access, v, speed_zero, speed_penalty)


def _check_condition_speed(sheet: dict, access, v: list[Violation],
                           speed_zero: bool, speed_penalty: int) -> None:
    mod = sheet.get("modifier", {}) or {}
    eff_speed = mod.get("speed", {}) or {}
    if not isinstance(eff_speed, dict):
        return
    if speed_zero:
        for mode, ft in eff_speed.items():
            if _int(ft) and ft != 0:
                v.append(Violation(DOMAIN, "condition-speed-not-zero", "illegal",
                                   f"active condition sets speed to 0; {mode} is {ft}ft",
                                   f"speed.{mode}"))
        return
    if not speed_penalty:
        return
    base = _base_effective_speeds(sheet, access)
    for mode, base_ft in base.items():
        expected = max(0, base_ft - speed_penalty)
        actual = eff_speed.get(mode)
        if _int(actual) and actual != expected:
            v.append(Violation(DOMAIN, "condition-speed-mismatch", "illegal",
                               f"{mode}: expected {expected}ft after the speed penalty, "
                               f"got {actual}ft", f"speed.{mode}"))


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


# ── starting treasure (re-derived from the chosen equipment bundle) ───────────


def _check_starting_treasure(sheet: dict, access, v: list[Violation]) -> None:
    """When the MODIFIER records the chosen starting-equipment bundle ids, independently re-derive the
    starting treasure as the SUM of every recorded bundle's gp grants in the DB and assert the sheet's
    coin gp matches. Starting wealth is the class bundle's gp PLUS the background bundle's gp (both
    bundles carry gp), so the expectation sums the ``kind='gp'`` entries of every recorded bundle.
    Grounded in the reference DB, never the deriver.

    The field is an object naming the chosen bundles (e.g. ``{"class": ..., "background": ...}``).
    Dormant when it is absent or records no bundle id. If any recorded id does not resolve to a bundle
    the treasure cannot be fully re-derived, so the check skips it rather than assert a partial sum
    (F05-T119)."""
    mod = sheet.get("modifier", {}) or {}
    bundles = mod.get("start_equipment_option")
    if not isinstance(bundles, dict):
        return
    option_ids = [oid for oid in (bundles.get("class"), bundles.get("background"))
                  if isinstance(oid, str) and oid]
    if not option_ids:
        return
    if not all(inventory_q.starting_equipment_bundle_exists(access, oid) for oid in option_ids):
        return
    treasure = mod.get("treasure", {}) or {}
    if not isinstance(treasure, dict):
        return
    actual_gp = treasure.get("gp", 0)
    if not _int(actual_gp):
        return
    expected_gp = sum(sum(inventory_q.starting_equipment_gp_grants(access, oid))
                      for oid in option_ids)
    if actual_gp != expected_gp:
        v.append(Violation(DOMAIN, "starting-treasure-mismatch", "illegal",
                           f"treasure gp {actual_gp} != re-derived starting gp {expected_gp} for "
                           f"bundles {option_ids}", "treasure.gp"))


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


# ── self-transform (full effective-stat replacement) ─────────────────────────


def _active_transform(sheet: dict, access) -> dict | None:
    """Return ``{creature_id, kind}`` for the first active self-transform state (a
    ``character_state`` whose source resolves to a grant owner and whose ``detail`` carries
    ``into`` + a valid ``transform`` kind), else None. Owner-resolution is re-derived here so
    the check stays independent of the deriver."""
    mod = sheet.get("modifier", {}) or {}
    states = mod.get("character_states", []) or []
    if not isinstance(states, list):
        return None
    for st in states:
        if not isinstance(st, dict):
            continue
        owner_kind = _owner_kind_for_source_type(st.get("source_type", ""))
        if owner_kind is None:
            continue
        owner_id = access.resolve(owner_kind, st.get("source"))
        if owner_id is None:
            continue
        detail = st.get("detail")
        detail = detail if isinstance(detail, dict) else {}
        into = detail.get("into")
        kind = detail.get("transform")
        if into and kind in _TRANSFORM_KINDS:
            return {"creature_id": into, "kind": kind,
                    "owner_kind": owner_kind, "owner_id": owner_id}
    return None


def _form_speeds(access, creature_id: str) -> dict:
    """The form's movement modes → feet (a formula_note mode resolves to the walk value)."""
    rows = creature_q.creature_speeds(access, creature_id)
    walk = None
    for r in rows:
        if r["movement_mode_id"] == "walk" and _int(r["feet"]):
            walk = r["feet"]
    out = {}
    for r in rows:
        mode, feet = r["movement_mode_id"], r["feet"]
        if _int(feet):
            out[mode] = feet
        elif r["formula_note"] and walk is not None:
            out[mode] = walk
    # Floor to a walk speed for a speed-less form, matching the deriver's fallback so a
    # form with no catalogued speeds does not false-flag a speed mismatch.
    return out or {"walk": 0}


def _form_senses(access, creature_id: str) -> dict:
    return {r["sense_id"]: r["range_ft"]
            for r in creature_q.creature_senses(access, creature_id)
            if _int(r["range_ft"])}


def _form_defenses(access, creature_id: str) -> dict:
    d = creature_q.creature_defenses(access, creature_id)
    return {
        "resistances": sorted(r["damage_type_id"] for r in d["resistance"] if r["damage_type_id"]),
        "immunities": sorted(r["damage_type_id"] for r in d["immunity_damage"]
                             if r["damage_type_id"]),
        "vulnerabilities": sorted(r["damage_type_id"] for r in d["vulnerability"]
                                  if r["damage_type_id"]),
        "condition_immunities": sorted(r["condition_id"] for r in d["immunity_condition"]
                                       if r["condition_id"]),
    }


def _form_save_mods(access, creature_id: str) -> dict:
    """The form's stat-block saving-throw modifier per full ability id, INDEPENDENTLY re-derived
    from the catalog: the form's ability modifier plus the FORM's own proficiency bonus
    (``creature.pb``) for a save the form is proficient in (``creature_save``, T63). Used for the
    self-transform higher-of (physical) and the form-authoritative saves (full). Reads DB facts
    only — never the deriver."""
    scores = {r["ability_id"]: r["score"]
              for r in creature_q.creature_abilities(access, creature_id) if _int(r["score"])}
    proficient = {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}
    row = creature_q.creature_row(access, creature_id)
    form_pb = row["pb"] if row is not None else None
    out = {}
    for aid, score in scores.items():
        modifier = (score - 10) // 2
        if aid in proficient and _int(form_pb):
            modifier += form_pb
        out[aid] = modifier
    return out


def _form_save_proficiencies(access, creature_id: str) -> set:
    """The full ability ids the form is proficient in for saves (``creature_save``). Under a
    PHYSICAL transform the character GAINS these proficiencies and applies their OWN PB to them."""
    return {r["ability_id"] for r in creature_q.creature_saves(access, creature_id)}


def _form_skill_mods(access, creature_id: str) -> dict:
    """The form's stat-block skill modifier per skill id (``creature_skill.bonus``), re-derived
    from the catalog for the self-transform higher-of (physical) / form-authoritative (full) skills.
    The keys are also the form's skill proficiencies, which a PHYSICAL transform GAINS (own PB)."""
    return {r["skill_id"]: r["bonus"]
            for r in creature_q.creature_skills(access, creature_id) if _int(r["bonus"])}


def _form_attacks(access, creature_id: str) -> dict:
    """The form's expected attacks keyed by name → (attack_bonus, damage, damage_type),
    re-derived from the creature's action rows (the same catalog source the deriver reads). An
    action counts as an attack when it carries an attack bonus; its damage is the stored dice
    string, else the flat average, else None — mirroring the deriver's replacement rule."""
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


def _check_transform(sheet: dict, access, transform: dict, v: list[Violation]) -> None:
    """Independently re-derive the transformed effective stats from the creature catalog and flag
    divergence. Enforces the retained-vs-replaced ability split (mental abilities retained under a
    PHYSICAL transform, all six replaced under FULL). A templated/unknown form is illegal. Never
    reads the deriver's output — every expectation comes from the catalog + CORE."""
    cid = transform["creature_id"]
    kind = transform["kind"]
    row = creature_q.creature_row(access, cid)
    if row is None:
        v.append(Violation(DOMAIN, "transform-creature-unknown", "illegal",
                           f"transform into {cid!r} does not resolve to a creature",
                           "character_states"))
        return
    if creature_q.creature_formulas(access, cid):
        v.append(Violation(DOMAIN, "transform-templated-not-form", "illegal",
                           f"transform target {cid!r} is owner-scaled (templated) and has no "
                           f"standalone stat block", "character_states"))
        return

    core = sheet.get("core", {}) or {}
    mod = sheet.get("modifier", {}) or {}
    core_abilities = core.get("abilities", {}) or {}

    # Effective abilities: form scores replace, except a PHYSICAL transform retains the
    # character's mental (Int/Wis/Cha) scores.
    form_scores = {r["ability_id"]: r["score"]
                   for r in creature_q.creature_abilities(access, cid) if _int(r["score"])}
    effective = mod.get("effective_abilities", {}) or {}
    if isinstance(effective, dict):
        for aid, actual in effective.items():
            if not _int(actual):
                continue
            full_aid = abilities_q.ability_id_for_short_key(access, aid) or aid
            retained = (kind == TRANSFORM_PHYSICAL and full_aid in _MENTAL_ABILITY_IDS)
            if retained:
                cdata = core_abilities.get(aid, {}) or {}
                final = cdata.get("final", 10) if isinstance(cdata, dict) else 10
                expected = final if _int(final) else 10
            else:
                expected = form_scores.get(full_aid)
            if expected is not None and actual != expected:
                v.append(Violation(DOMAIN, "transform-ability-mismatch", "illegal",
                                   f"{aid}: transformed effective {actual} != expected {expected} "
                                   f"({'retained mental' if retained else 'form'})",
                                   f"effective_abilities.{aid}"))

    # AC — the form's flat AC.
    ac = mod.get("armor_class")
    if _int(ac) and _int(row["ac_value"]) and ac != row["ac_value"]:
        v.append(Violation(DOMAIN, "transform-ac-mismatch", "illegal",
                           f"transformed armor_class {ac} != form AC {row['ac_value']}",
                           "armor_class"))

    # Speed — the form's speeds replace the character's.
    speed = mod.get("speed")
    if isinstance(speed, dict):
        expected_speed = _form_speeds(access, cid)
        for mode, exp in expected_speed.items():
            if speed.get(mode) != exp:
                v.append(Violation(DOMAIN, "transform-speed-mismatch", "illegal",
                                   f"speed {mode} {speed.get(mode)!r} != form {exp}", "speed"))
        for mode in speed:
            if mode not in expected_speed:
                v.append(Violation(DOMAIN, "transform-speed-mismatch", "illegal",
                                   f"speed {mode} {speed.get(mode)!r} not in the form's speeds",
                                   "speed"))

    # Senses — the form's senses replace the character's.
    senses = mod.get("effective_senses")
    if isinstance(senses, dict):
        expected_senses = _form_senses(access, cid)
        for sid, exp in expected_senses.items():
            if senses.get(sid) != exp:
                v.append(Violation(DOMAIN, "transform-sense-mismatch", "illegal",
                                   f"sense {sid} {senses.get(sid)!r} != form {exp}",
                                   "effective_senses"))
        for sid in senses:
            if sid not in expected_senses:
                v.append(Violation(DOMAIN, "transform-sense-mismatch", "illegal",
                                   f"sense {sid} {senses.get(sid)!r} not in the form's senses",
                                   "effective_senses"))

    # Defences — the form's block is authoritative (replace, not union with CORE permanent).
    eff_def = mod.get("effective_defenses")
    if isinstance(eff_def, dict):
        expected_def = _form_defenses(access, cid)
        for key, exp_list in expected_def.items():
            actual_list = eff_def.get(key, []) or []
            if not isinstance(actual_list, list):
                actual_list = []
            if sorted(actual_list) != exp_list:
                v.append(Violation(DOMAIN, "transform-defense-mismatch", "illegal",
                                   f"effective_defenses.{key} {sorted(actual_list)!r} != "
                                   f"form {exp_list!r}", f"effective_defenses.{key}"))

    # Attacks — the form's actions replace the character's; each expected form attack must be
    # present with the form's bonus/damage/damage_type. (`_check_attacks`/`_check_attack_damage`
    # are suspended under transform, so this is the sole attack assertion while transformed.)
    attacks = mod.get("attacks")
    if isinstance(attacks, list):
        expected_attacks = _form_attacks(access, cid)
        by_name = {a.get("name"): a for a in attacks if isinstance(a, dict) and a.get("name")}
        for name, (exp_bonus, exp_damage, exp_type) in expected_attacks.items():
            atk = by_name.get(name)
            if atk is None:
                v.append(Violation(DOMAIN, "transform-attack-missing", "illegal",
                                   f"form attack {name!r} not in transformed attacks", "attacks"))
                continue
            if (atk.get("attack_bonus") != exp_bonus or atk.get("damage") != exp_damage
                    or atk.get("damage_type") != exp_type):
                v.append(Violation(DOMAIN, "transform-attack-mismatch", "illegal",
                                   f"{name}: transformed attack "
                                   f"({atk.get('attack_bonus')!r}, {atk.get('damage')!r}, "
                                   f"{atk.get('damage_type')!r}) != form "
                                   f"({exp_bonus!r}, {exp_damage!r}, {exp_type!r})", "attacks"))


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    modifier = sheet.get("modifier")
    if modifier is None or not isinstance(modifier, dict):
        return v

    # A self-transform makes the form's stat block authoritative: the effective abilities, AC,
    # speed, senses, attacks and defences are the form's, not the character's. Under an active
    # transform, suspend the checks that would re-derive those from the character's CORE (they
    # would false-positive) and validate the form's block via `_check_transform` instead. The
    # ability-derived saves/skills/HP checks stay on, but transform-aware (fork 1 + 2).
    transform = _active_transform(sheet, access)

    _check_ac(sheet, v)
    _check_ac_bonus_dedup(sheet, v)
    _check_saves(sheet, access, v, transform)
    _check_skills(sheet, access, v, transform)
    _check_hp(sheet, access, v, transform)
    _check_hp_drain(sheet, access, v, transform)
    _check_form_hp_pool(sheet, access, v, transform)
    if transform is None:
        _check_attacks(sheet, access, v)
        _check_attack_damage(sheet, access, v)
        _check_granted_attacks(sheet, access, v)
        _check_effective_abilities(sheet, access, v)
        _check_defenses(sheet, v)
        _check_state_defenses(sheet, access, v)
        _check_condition_effects(sheet, access, v)
    else:
        _check_transform(sheet, access, transform, v)
    _check_size(sheet, access, v)
    _check_passives(sheet, v)
    _check_features(sheet, v)
    _check_feats(sheet, v)
    _check_prepared_spells(sheet, access, v)
    _check_states(sheet, access, v)
    _check_starting_treasure(sheet, access, v)

    return v
