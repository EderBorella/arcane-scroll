"""Defenses-domain DB facts: resistance, condition immunity, and save-advantage grants."""
from access.validator import ValidatorAccess


def resistance_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                      at_level: int | None = None) -> list:
    """Raw grant_resistance rows for an owner, optionally level-gated."""
    sql = ("SELECT id, damage_type_id, mode, choose_n, variant_axis, source_filter "
           "FROM grant_resistance WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def condition_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                     at_level: int | None = None) -> list:
    """Raw grant_condition rows for an owner, optionally level-gated."""
    sql = ("SELECT id, condition_id, effect "
           "FROM grant_condition WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def save_advantage_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                          at_level: int | None = None) -> list:
    """Raw grant_save_advantage rows for an owner, optionally level-gated."""
    sql = ("SELECT id, scope_kind, ability_id, note "
           "FROM grant_save_advantage WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def resistance_options(access: ValidatorAccess, grant_id: str) -> list[str]:
    """Damage-type option pool for a choose-mode resistance grant."""
    return [r["damage_type_id"]
            for r in access.db.q("SELECT damage_type_id FROM grant_resistance_option WHERE grant_id=?", grant_id)]


def damage_type_ids(access: ValidatorAccess) -> list[str]:
    """All known damage type IDs."""
    return [r["id"] for r in access.db.q("SELECT id FROM damage_type")]


def condition_ids(access: ValidatorAccess) -> list[str]:
    """All known condition ids."""
    return [r["id"] for r in access.db.q("SELECT id FROM condition")]


def variant_damage_type(access: ValidatorAccess, species_id: str, axis: str,
                        option_name: str) -> str | None:
    """Resolve a species_variant choice to its damage_type_id, e.g.
    dragonborn + 'draconic-ancestors' + 'Black' -> 'acid'."""
    return access.db.scalar(
        "SELECT damage_type_id FROM species_variant_option "
        "WHERE species_id=? AND axis=? AND option_name=?",
        species_id, axis, option_name)


def save_scope_for(access: ValidatorAccess, row: dict) -> str | None:
    """Map a grant_save_advantage row to a save_advantages scope string.
    ability scope -> ability abbreviation. concentration/death_save/spells -> keyword."""
    if row["scope_kind"] == "ability":
        abbr = access.db.scalar("SELECT abbrev FROM ability WHERE id=?", row["ability_id"])
        return abbr
    if row["scope_kind"] == "concentration":
        return "concentration"
    if row["scope_kind"] == "death_save":
        return "death"
    if row["scope_kind"] == "spells":
        return "spells"
    return None
