"""Size-domain DB facts: size ordinals, creature sizes, and size-effect grants.

Pure DB reads — no rule math.  The size catalog carries an ``ordinal`` column
(smaller sizes have lower ordinals), which lets a consumer apply a relative
size step by ordinal arithmetic and resolve back to a size id.
"""
from access.validator import ValidatorAccess


def size_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                at_level: int | None = None) -> list:
    """Raw grant_size rows for an owner, optionally level-gated."""
    sql = ("SELECT id, mode, step, size_id, variant, condition_kind "
           "FROM grant_size WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def size_ordinal(access: ValidatorAccess, size_id: str) -> int | None:
    """Ordinal of a size id (smaller = lower), or None if unknown."""
    return access.db.scalar("SELECT ordinal FROM size WHERE id=?", size_id)


def size_by_ordinal(access: ValidatorAccess, ordinal: int) -> str | None:
    """Size id at a given ordinal, or None if out of range."""
    return access.db.scalar("SELECT id FROM size WHERE ordinal=?", ordinal)


def size_ordinal_bounds(access: ValidatorAccess) -> tuple[int, int]:
    """(min_ordinal, max_ordinal) across the size catalog — the clamp range."""
    lo = access.db.scalar("SELECT MIN(ordinal) FROM size")
    hi = access.db.scalar("SELECT MAX(ordinal) FROM size")
    return (lo or 1, hi or 1)


def creature_size(access: ValidatorAccess, creature_id: str) -> str | None:
    """The size id of a creature (for set-from-creature transformations), or None."""
    return access.db.scalar("SELECT size_id FROM creature WHERE id=?", creature_id)
