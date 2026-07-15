"""Inventory-domain DB facts: catalog item identity, weapon properties, template validation,
and spell-scroll integrity. Pure DB queries — no business rules."""
from access.validator import ValidatorAccess


def get_slot_ids(access: ValidatorAccess) -> set[str]:
    """All valid equipment slot ids from the item_slot table."""
    return {row["id"] for row in access.db.q("SELECT id FROM item_slot")}


def item_exists(access: ValidatorAccess, name: str) -> bool:
    """True if a name resolves to either a catalog_item or a magic_item in the DB."""
    return (access.resolve("catalog_item", name) is not None or
            access.resolve("magic_item", name) is not None)


def item_is_two_handed(access: ValidatorAccess, catalog_item_id: str) -> bool:
    """True if a weapon has the 'two-handed' property in weapon_property_map."""
    return access.db.one(
        "SELECT 1 FROM weapon_property_map WHERE weapon_id=? AND property_id='two-handed'",
        catalog_item_id) is not None


def weapon_attack_facts(access: ValidatorAccess, weapon_id: str) -> dict | None:
    """Facts a consumer needs to compute a weapon's attack bonus, or None if the id is not a weapon.

    Returns ``{tier_id, range_class_id, finesse}`` where ``finesse`` is True when the weapon carries
    the finesse property. Pure DB reads — the ability-mod choice and proficiency-bonus rule live in
    the consuming check."""
    row = access.db.one(
        "SELECT tier_id, range_class_id FROM weapon WHERE id=?", weapon_id)
    if row is None:
        return None
    finesse = access.db.one(
        "SELECT 1 FROM weapon_property_map WHERE weapon_id=? AND property_id='finesse'",
        weapon_id) is not None
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


def extra_damage_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list:
    """Raw extra-damage grant_bonus rows for an owner (dice-only riders on attacks).

    Every ``grant_bonus`` row with ``target_kind='extra_damage'`` for the owner, with its
    dice and any ``condition_kind`` gate. Pure DB read — the consuming check owns the gate
    logic and the damage-string match."""
    return access.db.q(
        "SELECT id, die_count, die_faces, damage_type_id, condition_kind FROM grant_bonus "
        "WHERE owner_kind=? AND owner_id=? AND target_kind='extra_damage'",
        owner_kind, owner_id)


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
