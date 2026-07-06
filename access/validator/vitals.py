"""Vitals-domain DB facts: class hit-die faces and HP-grant riders (e.g. a species' flat/per-level
HP bonus)."""
from access.validator import ValidatorAccess


def class_hit_die(access: ValidatorAccess, class_id: str) -> int | None:
    """A class's hit-die face count, or None if the class is unknown."""
    return access.db.scalar("SELECT hit_die_faces FROM class WHERE id=?", class_id)


def hp_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list:
    """Flat/per-level HP grant rows for an owner (e.g. a species HP rider)."""
    return access.db.q(
        "SELECT flat, per_level FROM grant_hp WHERE owner_kind=? AND owner_id=?", owner_kind, owner_id)
