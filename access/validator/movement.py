"""Movement-domain DB facts: grant_speed rows, species base walk speed, movement modes, and class speed bonuses."""
from access.validator import ValidatorAccess


def speed_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                 at_level: int | None = None) -> list:
    """Raw grant_speed rows for an owner, optionally level-gated."""
    sql = ("SELECT movement_mode_id, feet, equals_walk, sets_total, additive "
           "FROM grant_speed WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def species_base_walk(access: ValidatorAccess, species_id: str) -> int | None:
    """The base walk speed for a species (base_walk_speed column)."""
    return access.db.scalar("SELECT base_walk_speed FROM species WHERE id=?", species_id)


def lineage_parent_species(access: ValidatorAccess, lineage_id: str) -> str | None:
    """The species id a lineage belongs to, or None if unknown."""
    return access.db.scalar("SELECT species_id FROM lineage WHERE id=?", lineage_id)


def movement_mode_ids(access: ValidatorAccess) -> list[str]:
    """All known movement mode ids."""
    return [r["id"] for r in access.db.q("SELECT id FROM movement_mode")]


def class_speed_bonus(access: ValidatorAccess, class_id: str, level: int) -> int | None:
    """Highest bonus from class_resource_level at or below the given level for a speed-related
    class resource (e.g. Unarmored Movement). Only resources whose name includes 'movement'
    or 'speed' are considered — other class_resource.bonus columns (like Rage Damage) are
    not speed bonuses."""
    return access.db.scalar(
        "SELECT MAX(crl.bonus) FROM class_resource_level crl "
        "JOIN class_resource cr ON cr.id=crl.resource_id "
        "WHERE cr.owner_kind='class' AND cr.owner_id=? AND crl.level<=? AND crl.bonus IS NOT NULL "
        "AND (cr.name LIKE '%movement%' OR cr.name LIKE '%Movement%' "
        "     OR cr.name LIKE '%speed%' OR cr.name LIKE '%Speed%')",
        class_id, level)
