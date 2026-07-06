"""Abilities-domain DB facts: ability identity, background boost lists, and the standard score cap."""
from access.validator import ValidatorAccess


def ability_id(access: ValidatorAccess, key: str) -> str | None:
    """Resolve a sheet ability key (id, abbrev, or name) to the ability id, or None if unknown."""
    if not isinstance(key, str):
        return None
    return access.db.scalar(
        "SELECT id FROM ability WHERE id=? COLLATE NOCASE OR abbrev=? COLLATE NOCASE OR name=? COLLATE NOCASE",
        key, key, key)


def all_ability_ids(access: ValidatorAccess) -> list[str]:
    """Every ability id in the rulebook, in a stable order."""
    return [row["id"] for row in access.db.q("SELECT id FROM ability ORDER BY id")]


def background_boost_abilities(access: ValidatorAccess, background_id: str) -> list[str]:
    """The ability ids a background may boost, in the background's declared order."""
    return [row["ability_id"] for row in access.db.q(
        "SELECT ability_id FROM background_ability WHERE background_id=? ORDER BY ordinal", background_id)]


def standard_ability_cap(access: ValidatorAccess) -> int | None:
    """The standard ability score cap (falls back to 20 if the ASI grant row is missing)."""
    cap = access.db.scalar(
        "SELECT cap FROM grant_ability_increase WHERE owner_kind='feat' "
        "AND owner_id='ability-score-improvement' LIMIT 1")
    return cap if cap is not None else 20
