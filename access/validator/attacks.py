"""Attacks-domain DB facts: grant_attack rows for an owner (a spell/effect, feat, etc.).

Pure DB reads — no rule math. The ``ability_mode`` (e.g. ``'spellcasting'``) and the attack/damage
totals are resolved by the consumer (deriver / validator), each independently."""
from access.validator import ValidatorAccess


def attack_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                  at_level: int | None = None) -> list:
    """Raw grant_attack rows for an owner, optionally level-gated (a NULL gained_at_level is
    always included)."""
    sql = ("SELECT id, owner_kind, owner_id, gained_at_level, name, ability_mode, "
           "die_count, die_faces, damage_type, properties "
           "FROM grant_attack WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    sql += " ORDER BY id"
    return access.db.q(sql, *params)
