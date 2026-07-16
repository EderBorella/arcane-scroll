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


def state_hp_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list:
    """Flat/per-level HP grant rows for an owner WITH their condition_kind gate.

    For the MODIFIER state-HP re-derivation: a state-gated HP boost or a drain/curse that lowers max
    HP (a negative amount). Pure DB read — the gate rule and sign handling live in the check (T58)."""
    return access.db.q(
        "SELECT flat, per_level, condition_kind FROM grant_hp WHERE owner_kind=? AND owner_id=?",
        owner_kind, owner_id)
