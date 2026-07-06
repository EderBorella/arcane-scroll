"""Identity-domain DB facts: class/subclass/species/background structure + XP thresholds."""
from access.validator import ValidatorAccess


def subclass_parent(access: ValidatorAccess, subclass_id: str) -> str | None:
    """The class id a subclass belongs to, or None if the subclass is unknown."""
    return access.db.scalar("SELECT class_id FROM subclass WHERE id=?", subclass_id)


def subclass_unlock_level(access: ValidatorAccess, class_id: str) -> int | None:
    """The level a class gains its subclass, or None if the class is unknown."""
    return access.db.scalar("SELECT subclass_level FROM class WHERE id=?", class_id)


def species_creature_type(access: ValidatorAccess, species_id: str) -> str | None:
    """The creature-type id of a species, or None if unknown."""
    return access.db.scalar("SELECT creature_type_id FROM species WHERE id=?", species_id)


def xp_min(access: ValidatorAccess, level: int) -> int | None:
    """The minimum XP for a character level, or None if the level isn't in the table."""
    return access.db.scalar("SELECT xp_min FROM xp_level WHERE level=?", level)
