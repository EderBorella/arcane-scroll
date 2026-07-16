"""Starting-equipment option reads for the choice grammar: the mutually-exclusive equipment bundles an
owner (a class or a background) offers, and the line entries inside a chosen bundle. Pure DB reads —
no rule math (resolving a bundle into a concrete inventory is the deriver's concern)."""
from access.generator import GeneratorAccess


def starting_equipment_options(access: GeneratorAccess, owner_kind: str, owner_id: str) -> list:
    """The starting-equipment option bundles an owner offers, as (id, owner_kind, owner_id, label)
    rows ordered by id — the grammar picks one bundle. `owner_kind` is 'class' or 'background'."""
    return access.db.q(
        "SELECT id, owner_kind, owner_id, label FROM start_equipment_option "
        "WHERE owner_kind=? AND owner_id=? ORDER BY id", owner_kind, owner_id)


def starting_equipment_entries(access: GeneratorAccess, option_id: str) -> list:
    """The line entries inside one equipment bundle, ordered by sort_order. Each entry's `kind`
    tells how to read it — a concrete item (catalog_item_id + quantity), a gp amount (gp_amount), a
    tool-category choice (tool_category_id), a spellcasting-focus choice (focus_type_id), or a
    proficiency-referenced pick — returned as raw columns for the deriver to interpret."""
    return access.db.q(
        "SELECT id, option_id, sort_order, kind, catalog_item_id, quantity, gp_amount, "
        "tool_category_id, focus_type_id, note FROM start_equipment_entry WHERE option_id=? "
        "ORDER BY sort_order, id", option_id)


def item_name(access: GeneratorAccess, item_id: str | None) -> str | None:
    """The display name of a catalog item, or None for an unknown / missing id — used to turn a
    bundle's concrete item entry (a catalog item id) into a named inventory record. Pure DB read."""
    if item_id is None:
        return None
    return access.db.scalar("SELECT name FROM catalog_item WHERE id=?", item_id)


# ── catalog-fact reads for inventory enrichment (F05-T80) ─────────────────────
# Raw catalog rows the inventory assembly folds onto an item record so a generated inventory carries
# the same reference facts as the corpus. Pure DB reads — shaping the rows into the inventory record
# (formatting a damage string, choosing which facts to attach) is the assembly's concern, not this
# layer's.


def catalog_item_facts(access: GeneratorAccess, item_id: str | None) -> dict | None:
    """The base catalog facts of an item — its ``kind`` (weapon / armor / gear / …), catalog
    ``category_id``, and ``weight`` in pounds — or None for an unknown / missing id.

    ``weight`` degrades to None when the column is absent (a minimal reference dataset that does not
    model item weight) — the same graceful-degradation idiom the spell-row reader uses."""
    if item_id is None:
        return None
    row = access.db.one("SELECT kind, category_id FROM catalog_item WHERE id=?", item_id)
    if row is None:
        return None
    return {"kind": row["kind"], "category_id": row["category_id"],
            "weight": _weight_lb(access, item_id)}


def _weight_lb(access: GeneratorAccess, item_id: str):
    try:
        return access.db.scalar("SELECT weight_lb FROM catalog_item WHERE id=?", item_id)
    except Exception:
        return None


def weapon_facts(access: GeneratorAccess, item_id: str) -> dict | None:
    """A weapon's combat facts (base damage dice + type, mastery property, range class) plus its
    weapon-property id list, or None when the id is not a weapon. Pure DB reads — the dice string is
    formatted by the consumer."""
    row = access.db.one(
        "SELECT dmg_dice_count, dmg_die_faces, dmg_flat, damage_type_id, mastery_id, range_class_id "
        "FROM weapon WHERE id=?", item_id)
    if row is None:
        return None
    props = [r["property_id"] for r in access.db.q(
        "SELECT property_id FROM weapon_property_map WHERE weapon_id=? ORDER BY property_id", item_id)]
    return {"dmg_dice_count": row["dmg_dice_count"], "dmg_die_faces": row["dmg_die_faces"],
            "dmg_flat": row["dmg_flat"], "damage_type_id": row["damage_type_id"],
            "mastery_id": row["mastery_id"], "range_class_id": row["range_class_id"],
            "properties": props}


def armor_facts(access: GeneratorAccess, item_id: str) -> dict | None:
    """An armour's defensive facts (category, base AC, Dex cap, shield AC bonus, Strength requirement,
    stealth penalty), or None when the id is not armour. Pure DB reads."""
    row = access.db.one(
        "SELECT category_id, base_ac, dex_cap, ac_bonus, strength_req, stealth_disadvantage "
        "FROM armor WHERE id=?", item_id)
    if row is None:
        return None
    return {"category_id": row["category_id"], "base_ac": row["base_ac"], "dex_cap": row["dex_cap"],
            "ac_bonus": row["ac_bonus"], "strength_req": row["strength_req"],
            "stealth_disadvantage": row["stealth_disadvantage"]}
