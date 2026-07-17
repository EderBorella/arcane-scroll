"""Condition-effect DB facts: the typed mechanical effects each condition imposes,
plus the mapping from an active state to its governing condition.

Pure queries — no rule math. The deriver and the validator each read these rows
and apply the effects independently, so they cross-check rather than share logic.
"""
from access.validator import ValidatorAccess


def condition_effects(access: ValidatorAccess, condition_id: str) -> list:
    """All condition_effect rows for one condition."""
    return access.db.q(
        "SELECT effect_kind, target_kind, target_id, modifier, source_scope "
        "FROM condition_effect WHERE condition_id = ?", condition_id)


def leveled_condition_id(access: ValidatorAccess) -> str | None:
    """The single condition whose effects scale per level (a ``<coeff>_per_level``
    modifier formula). Returns None unless exactly one such condition exists."""
    rows = access.db.q(
        "SELECT DISTINCT condition_id FROM condition_effect "
        r"WHERE modifier LIKE '%\_per\_level' ESCAPE '\'")
    return rows[0]["condition_id"] if len(rows) == 1 else None


def condition_id_for_state(access: ValidatorAccess, state_id: str,
                           has_level: bool = False) -> str | None:
    """Map an active condition-state to its governing condition id.

    Most condition-states share their id with the condition, so the resolver maps
    them directly. A leveled state whose id differs from its condition resolves to
    the single per-level condition (identified from the effect data, not by name)."""
    direct = access.resolve("condition", state_id)
    if direct:
        return direct
    if has_level:
        return leveled_condition_id(access)
    return None
