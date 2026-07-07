"""Features-domain DB facts: class/subclass features, species traits, detail options, and
powers anchored to features."""
from access.validator import ValidatorAccess


def class_features(access: ValidatorAccess, class_id: str, level: int) -> list:
    """Features gained by a class at or below the given level."""
    return access.db.q(
        "SELECT id, class_id, level, name FROM class_feature WHERE class_id=? AND level<=?",
        class_id, level)


def subclass_features(access: ValidatorAccess, subclass_id: str, class_level: int) -> list:
    """Features gained by a subclass at or below the given class level."""
    return access.db.q(
        "SELECT id, subclass_id, class_level, name FROM subclass_feature WHERE subclass_id=? AND class_level<=?",
        subclass_id, class_level)


def species_traits(access: ValidatorAccess, species_id: str) -> list:
    """Traits of a species."""
    return access.db.q(
        "SELECT id, species_id, name FROM species_trait WHERE species_id=?", species_id)


def detail_options(access: ValidatorAccess, owner_kind: str, owner_id: str,
                   axis: str | None = None) -> list:
    """Detail options for a class or subclass, optionally filtered by axis."""
    if axis is not None:
        return access.db.q(
            "SELECT id, owner_kind, owner_id, axis, name, rechoose "
            "FROM detail_option WHERE owner_kind=? AND owner_id=? AND axis=?",
            owner_kind, owner_id, axis)
    return access.db.q(
        "SELECT id, owner_kind, owner_id, axis, name, rechoose "
        "FROM detail_option WHERE owner_kind=? AND owner_id=?", owner_kind, owner_id)


def feature_powers(access: ValidatorAccess, feature_kind: str, feature_id: str) -> list:
    """Powers anchored to a specific feature (class_feature or subclass_feature)."""
    return access.db.q(
        "SELECT id, owner_kind, owner_id, gained_at_level, feature_kind, feature_id, name, "
        "use_limit, resource_kind, resource_id, resource_cost "
        "FROM power WHERE feature_kind=? AND feature_id=?", feature_kind, feature_id)
