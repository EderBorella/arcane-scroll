"""Feats-domain DB facts: feat identity/category/repeatability, prerequisite rows, ASI/Epic-Boon
slot counts sourced from class features, and origin-feat grant detection (background/species)."""
from access.validator import ValidatorAccess


def feat_row(access: ValidatorAccess, feat_id: str):
    """The feat's (id, name, category, repeatable) row, or None if unknown."""
    return access.db.one("SELECT id, name, category, repeatable FROM feat WHERE id=?", feat_id)


def feat_prereqs(access: ValidatorAccess, feat_id: str) -> list:
    """The feat's feat_prereq rows -- any_of_group, kind, min_level, ability_id, min_score,
    armor_category_id, note. AND across distinct any_of_group values, OR within a group (the
    check applies that grouping; this just returns the raw rows)."""
    return access.db.q(
        "SELECT any_of_group, kind, min_level, ability_id, min_score, armor_category_id, note "
        "FROM feat_prereq WHERE feat_id=?", feat_id)


def asi_slots(access: ValidatorAccess, class_id: str, level: int) -> int:
    """Count of Ability Score Improvement / Epic Boon class_feature rows a class has gained at or
    below `level` -- the number of feat-or-raw-ability-increase slots it has opened up."""
    return access.db.scalar(
        "SELECT COUNT(*) FROM class_feature WHERE class_id=? AND level<=? "
        "AND name IN ('Ability Score Improvement','Epic Boon')", class_id, level)


def grants_origin_feat(access: ValidatorAccess, owner_kind: str, owner_id: str) -> bool:
    """True if the owner (e.g. a species) has a grant_feat row conferring an origin-category feat."""
    return access.db.scalar(
        "SELECT 1 FROM grant_feat WHERE owner_kind=? AND owner_id=? AND from_category='origin' LIMIT 1",
        owner_kind, owner_id) is not None


def background_origin_feat(access: ValidatorAccess, background_id: str) -> str | None:
    """The origin feat id a background confers (background.feat_id), or None. This -- not
    grant_feat -- is the DB's actual source of a background's origin-feat grant."""
    return access.db.scalar("SELECT feat_id FROM background WHERE id=?", background_id)
