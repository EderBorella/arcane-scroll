"""Catalog name/enumeration reads the CORE deriver consumes to turn choice ids into a sheet.

A generator holds its selections as catalog ids (the option readers in this package return id-keyed
rows); the sheet, by contrast, carries display forms. These readers close that gap — an id->name
lookup over an allow-listed dimension table, plus the full ability and skill enumerations the deriver
walks to emit one entry per ability / per skill. Pure DB reads — no rule math."""
from access.generator import GeneratorAccess

# Dimension tables the id->name lookup may read — structure (table names), not content, allow-listed
# so the interpolated identifier is never caller-controlled SQL.
_NAME_TABLES = {
    "species", "class", "subclass", "background", "feat", "size", "creature_type",
    "armor_category", "weapon_tier", "tool", "skill", "ability", "lineage", "damage_type",
    "condition", "sense", "movement_mode",
}


def name_of(access: GeneratorAccess, table: str, id_value: str | None) -> str | None:
    """The display name of a catalog row, or None for an unknown id / missing row. `table` is
    validated against the allow-list — an unknown dimension raises rather than interpolating it."""
    if id_value is None:
        return None
    if table not in _NAME_TABLES:
        raise ValueError(f"name_of: unknown dimension {table!r}")
    return access.db.scalar(f"SELECT name FROM {table} WHERE id=?", id_value)


def list_abilities(access: GeneratorAccess) -> list:
    """Every ability in the rulebook, as (id, name, abbrev) rows ordered by id — the deriver emits one
    ability/saving-throw entry per row."""
    return access.db.q("SELECT id, name, abbrev FROM ability ORDER BY id")


def list_skills(access: GeneratorAccess) -> list:
    """Every skill in the rulebook, as (id, name, ability_id) rows ordered by id — the deriver emits
    one skill entry per row."""
    return access.db.q("SELECT id, name, ability_id FROM skill ORDER BY id")
