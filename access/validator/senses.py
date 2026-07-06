"""Senses-domain DB facts: grant_sense rows for an owner (species, class, subclass, feat, etc.)."""
from access.validator import ValidatorAccess


def sense_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                 at_level: int | None = None) -> list:
    """Raw grant_sense rows for an owner, optionally level-gated."""
    sql = ("SELECT sense_id, range_ft, extends_existing "
           "FROM grant_sense WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def sense_ids(access: ValidatorAccess) -> list[str]:
    """All known sense ids (for the `senses` key set — detect unknown sense keys on a sheet)."""
    return [r["id"] for r in access.db.q("SELECT id FROM sense")]
