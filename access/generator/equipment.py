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
