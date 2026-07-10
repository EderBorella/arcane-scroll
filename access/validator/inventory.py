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
