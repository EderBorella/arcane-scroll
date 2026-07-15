"""Abilities-domain DB facts: ability identity, background boost lists, and the standard score cap."""
from access import primitives
from access.validator import ValidatorAccess


def ability_id(access: ValidatorAccess, key: str) -> str | None:
    """Resolve a sheet ability key (id, abbrev, or name) to the ability id, or None if unknown."""
    if not isinstance(key, str):
        return None
    return access.db.scalar(
        "SELECT id FROM ability WHERE id=? COLLATE NOCASE OR abbrev=? COLLATE NOCASE OR name=? COLLATE NOCASE",
        key, key, key)


def ability_id_for_short_key(access: ValidatorAccess, key: str) -> str | None:
    """Map a CORE short ability key (its abbreviation) to the canonical DB ability id.

    A sheet keys its abilities and saving throws by the short code, while the reference DB --
    and every grant's target/ability id -- keys them by the full id (the canonical form). This
    resolves the short code to that full id (matched on ``ability.abbrev`` case-insensitively),
    or None if it matches no ability's abbreviation. Use this to normalise a short key before
    comparing it to a DB-sourced full id."""
    if not isinstance(key, str):
        return None
    return access.db.scalar("SELECT id FROM ability WHERE abbrev=? COLLATE NOCASE", key)


def all_ability_ids(access: ValidatorAccess) -> list[str]:
    """Every ability id in the rulebook, in a stable order."""
    return [row["id"] for row in access.db.q("SELECT id FROM ability ORDER BY id")]


def background_boost_abilities(access: ValidatorAccess, background_id: str) -> list[str]:
    """The ability ids a background may boost, in the background's declared order."""
    return [row["ability_id"] for row in access.db.q(
        "SELECT ability_id FROM background_ability WHERE background_id=? ORDER BY ordinal", background_id)]


def granted_ability_sets(access: ValidatorAccess, owner_kind: str, owner_id: str,
                         at_level: int | None = None) -> list[dict]:
    """grant_ability_set rows an owner (species/feat/class/subclass/magic_item/...) confers, each as
    {ability_id, score, mode}.

    ``mode`` is 'set' (a true override of the score) or 'floor' (a minimum the score is raised to);
    ``ability_id`` is the canonical full DB id. If ``at_level`` is given, only rows gained at or
    below it are included (a NULL gained_at_level always applies) — the same level gating the
    saving-throws grant query uses. Pure DB read — the override/floor arithmetic lives in the check."""
    return [{"ability_id": r["ability_id"], "score": r["score"], "mode": r["mode"]}
            for r in primitives.grants_for(access.db, "grant_ability_set", owner_kind, owner_id,
                                           at_level)]


def item_ability_sets(access: ValidatorAccess, magic_item_id: str) -> list[dict]:
    """grant_ability_set rows an attuned magic item confers — see `granted_ability_sets`."""
    return granted_ability_sets(access, "magic_item", magic_item_id)


def standard_ability_cap(access: ValidatorAccess) -> int | None:
    """The standard ability score cap (falls back to 20 if the ASI grant row is missing)."""
    cap = access.db.scalar(
        "SELECT cap FROM grant_ability_increase WHERE owner_kind='feat' "
        "AND owner_id='ability-score-improvement' LIMIT 1")
    return cap if cap is not None else 20
