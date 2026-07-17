"""Inventory-domain DB facts: catalog item identity, weapon properties, template validation,
and single-use casting item integrity. Pure DB queries — no business rules."""
from access.validator import ValidatorAccess


def get_slot_ids(access: ValidatorAccess) -> set[str]:
    """All valid equipment slot ids from the item_slot table."""
    return {row["id"] for row in access.db.q("SELECT id FROM item_slot")}


def item_exists(access: ValidatorAccess, name: str) -> bool:
    """True if a name resolves to either a catalog_item or a magic_item in the DB."""
    return (access.resolve("catalog_item", name) is not None or
            access.resolve("magic_item", name) is not None)


def item_is_magic(access: ValidatorAccess, name: str) -> bool:
    """True if a name resolves to a magic_item. A magic item's slot and combat facts derive from the
    magic item itself, not a mundane base row, so the slot-grounding / enrichment re-derivation skips
    it. Pure name resolution."""
    return access.resolve("magic_item", name) is not None


def catalog_kind(access: ValidatorAccess, item_id: str) -> str | None:
    """The catalog ``kind`` of an item (``weapon`` / ``armor`` / ``gear`` / …), or None for an
    unknown id. Pure DB read — the slot/enrichment rule stays with the consuming check."""
    return access.db.scalar("SELECT kind FROM catalog_item WHERE id=?", item_id)


def armor_facts(access: ValidatorAccess, item_id: str) -> dict | None:
    """An armour item's defensive facts (category, base AC, Dex cap, shield AC bonus, Strength
    requirement), or None when the id has no ``armor`` row. Pure DB reads — the consuming check owns
    the wear/hold slot rule and the fact comparison. Mirrors the generator-side reader so the
    validator re-derives the same DB facts through its OWN access surface (no cross-consumer import)."""
    row = access.db.one(
        "SELECT category_id, base_ac, dex_cap, ac_bonus, strength_req FROM armor WHERE id=?",
        item_id)
    if row is None:
        return None
    return {"category_id": row["category_id"], "base_ac": row["base_ac"],
            "dex_cap": row["dex_cap"], "ac_bonus": row["ac_bonus"],
            "strength_req": row["strength_req"]}


def weapon_damage_facts(access: ValidatorAccess, item_id: str) -> dict | None:
    """A weapon's base damage facts (dice as an ``NdM`` string, damage-type id, mastery id) plus its
    weapon-property id set, or None when the id is not a weapon. Pure DB reads — the dice string is
    formatted here from the dice-triple, but no rule math (crit, ability mod) is applied."""
    row = access.db.one(
        "SELECT dmg_dice_count, dmg_die_faces, damage_type_id, mastery_id FROM weapon WHERE id=?",
        item_id)
    if row is None:
        return None
    dc, df = row["dmg_dice_count"], row["dmg_die_faces"]
    dice = f"{dc}d{df}" if dc and df else None
    props = {r["property_id"] for r in access.db.q(
        "SELECT property_id FROM weapon_property_map WHERE weapon_id=?", item_id)}
    return {"damage_dice": dice, "damage_type_id": row["damage_type_id"],
            "mastery_id": row["mastery_id"], "properties": props}


def item_is_two_handed(access: ValidatorAccess, catalog_item_id: str) -> bool:
    """True if a weapon has the 'two-handed' property in weapon_property_map."""
    return access.db.one(
        "SELECT 1 FROM weapon_property_map WHERE weapon_id=? AND property_id='two-handed'",
        catalog_item_id) is not None


def base_weapon_id_for_item(access: ValidatorAccess, item_id: str) -> str | None:
    """The canonical base weapon-stats id for a magic weapon that carries no stats row of its own.

    A magic weapon may be catalogued as a weapon yet have no ``weapon`` row (no dice/tier/
    properties); its underlying base weapon(s) are recorded in ``magic_item_template.base_item_id``.
    A template may name SEVERAL bases (the same magic weapon can be built on any of them). To keep the
    reader-side result deterministic — so the attack-bonus and extra-damage rider re-derivation is not
    silently skipped for a multi-base template — this returns a single CANONICAL base: among the
    distinct bases that resolve to a real ``weapon`` row, the lowest id. Returns None only when the
    template names no base that resolves to a weapon row. Pure DB read; no schema/DB change — the
    attack rule stays with the consuming deriver/check."""
    rows = access.db.q(
        "SELECT DISTINCT base_item_id FROM magic_item_template "
        "WHERE template_id=? AND base_kind='weapon' AND base_item_id IS NOT NULL", item_id)
    weapon_bases = sorted(
        r["base_item_id"] for r in rows
        if access.db.one("SELECT 1 FROM weapon WHERE id=?", r["base_item_id"]) is not None)
    return weapon_bases[0] if weapon_bases else None


def weapon_attack_facts(access: ValidatorAccess, weapon_id: str) -> dict | None:
    """Facts a consumer needs to compute a weapon's attack bonus, or None if the id is not a weapon.

    Returns ``{tier_id, range_class_id, finesse}`` where ``finesse`` is True when the weapon carries
    the finesse property. Pure DB reads — the ability-mod choice and proficiency-bonus rule live in
    the consuming check. A stats-less magic weapon (no ``weapon`` row) falls back to its unambiguous
    base weapon's facts, so the consuming check can re-derive its attack bonus (F05-T56)."""
    row = access.db.one(
        "SELECT tier_id, range_class_id FROM weapon WHERE id=?", weapon_id)
    facts_id = weapon_id
    if row is None:
        base_id = base_weapon_id_for_item(access, weapon_id)
        if base_id is None:
            return None
        row = access.db.one(
            "SELECT tier_id, range_class_id FROM weapon WHERE id=?", base_id)
        if row is None:
            return None
        facts_id = base_id
    finesse = access.db.one(
        "SELECT 1 FROM weapon_property_map WHERE weapon_id=? AND property_id='finesse'",
        facts_id) is not None
    return {"tier_id": row["tier_id"], "range_class_id": row["range_class_id"],
            "finesse": finesse}


def weapon_attack_item_bonuses(access: ValidatorAccess, magic_item_id: str) -> list[int]:
    """Weapon-attack bonus values a magic item confers, one per grant_bonus row.

    Every ``grant_bonus`` row with ``target_kind='weapon_attack'`` for the item, as its raw integer
    value list (NULLs coerced to 0). Pure DB read — the consuming check owns summing/applying them."""
    rows = access.db.q(
        "SELECT value FROM grant_bonus WHERE owner_kind='magic_item' AND owner_id=? "
        "AND target_kind='weapon_attack'", magic_item_id)
    return [(r["value"] or 0) for r in rows]


def requires_attunement(access: ValidatorAccess, magic_item_id: str) -> bool:
    """True if a magic item requires attunement (its ``magic_item.requires_attunement`` flag is set).

    Pure DB read. A missing row or NULL flag reads as False (no attunement required)."""
    return bool(access.db.scalar(
        "SELECT requires_attunement FROM magic_item WHERE id=?", magic_item_id))


def extra_damage_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list:
    """Raw extra-damage grant_bonus rows for an owner (dice-only riders on attacks).

    Every ``grant_bonus`` row with ``target_kind='extra_damage'`` for the owner, with its
    dice and any ``condition_kind`` gate. Pure DB read — the consuming check owns the gate
    logic and the damage-string match."""
    return access.db.q(
        "SELECT id, die_count, die_faces, damage_type_id, condition_kind FROM grant_bonus "
        "WHERE owner_kind=? AND owner_id=? AND target_kind='extra_damage'",
        owner_kind, owner_id)


def starting_equipment_bundle_exists(access: ValidatorAccess, option_id: str) -> bool:
    """True if a starting-equipment bundle id resolves to a ``start_equipment_option`` row. Pure DB
    read — the consuming check decides what to do when a recorded bundle id is unknown."""
    return access.db.one(
        "SELECT 1 FROM start_equipment_option WHERE id=?", option_id) is not None


def starting_equipment_gp_grants(access: ValidatorAccess, option_id: str) -> list[int]:
    """The gp amounts of a starting-equipment bundle's coin entries, one per ``start_equipment_entry``
    row with ``kind='gp'`` (NULLs coerced to 0). Pure DB read — the consuming check owns summing them
    and comparing the total to the sheet's coin gp."""
    rows = access.db.q(
        "SELECT gp_amount FROM start_equipment_entry WHERE option_id=? AND kind='gp'", option_id)
    return [(r["gp_amount"] or 0) for r in rows]


def template_valid(access: ValidatorAccess, template_name: str,
                   base_item_name: str | None) -> str | None:
    """Check template validity. Returns None if valid, or an error string if invalid."""
    row = access.db.one(
        "SELECT base_kind, base_item_id FROM magic_item_template WHERE template_id=?",
        template_name)
    if row is None:
        return f"unknown template: {template_name!r}"

    if base_item_name is None:
        return None

    base_kind = row["base_kind"]
    base_id = access.resolve("catalog_item", base_item_name)
    if base_id is None:
        return f"unknown base_item: {base_item_name!r}"

    item_kind = access.db.scalar(
        "SELECT kind FROM catalog_item WHERE id=?", base_id)
    if item_kind is None:
        item_kind = _infer_kind(access, base_id)

    if item_kind is None:
        return None

    if item_kind != base_kind:
        return f"template {template_name!r} expects base_kind={base_kind!r}, "
        f"got {item_kind!r} for {base_item_name!r}"
    return None


def _infer_kind(access: ValidatorAccess, catalog_item_id: str) -> str | None:
    if access.db.one("SELECT 1 FROM weapon WHERE id=?", catalog_item_id):
        return "weapon"
    if access.db.one("SELECT 1 FROM magic_item WHERE id=?", catalog_item_id):
        return "wondrous"
    return None
