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


def scoped_weapon_bonuses(access: ValidatorAccess, owner_kind: str, owner_id: str,
                          grant_id: str) -> list:
    """``grant_bonus`` rows SCOPED to one granted attack (``target_id`` == the grant's id) for the
    weapon attack/damage targets. A scoped weapon bonus folds into that granted attack only (an
    unscoped row — NULL target_id — is a character-wide weapon bonus, excluded here). Pure DB read —
    the consumer sums the values by target_kind."""
    return access.db.q(
        "SELECT target_kind, value FROM grant_bonus WHERE owner_kind=? AND owner_id=? "
        "AND target_id=? AND target_kind IN ('weapon_attack','weapon_damage') ORDER BY id",
        owner_kind, owner_id, grant_id)
