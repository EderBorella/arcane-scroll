"""Resources domain: the class-resource ladder (per-level use counts of class/subclass resources)
and the ``grant_resource`` use-pool spine (a use pool a species/lineage/class/other source confers).

Pure DB facts — the per-level maximum and the raw grant rows are looked up here; the rule of which
resources become a sheet ``resource_budgets`` entry, and how a formula use-pool's maximum is computed
(a fixed count, the proficiency bonus, or an ability modifier), live in the consumer so the deriver
and the validator each re-derive it independently."""
from access import primitives
from access.validator import ValidatorAccess


def count_class_resources(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list[dict]:
    """Resources an owner (class/subclass) confers that have a COUNT ladder — i.e. at least one
    ``class_resource_level`` row with a non-null ``count`` (a whole-number use pool, not a die or a
    flat bonus). Returned as ``{id, name}`` ordered by id. Pure DB read."""
    out: list[dict] = []
    for r in access.db.q(
            "SELECT id, name FROM class_resource WHERE owner_kind=? AND owner_id=? ORDER BY id",
            owner_kind, owner_id):
        if access.db.one(
                "SELECT 1 FROM class_resource_level WHERE resource_id=? AND count IS NOT NULL LIMIT 1",
                r["id"]) is not None:
            out.append({"id": r["id"], "name": r["name"]})
    return out


def resource_count_at(access: ValidatorAccess, resource_id: str, level: int) -> int | None:
    """The count-valued ladder maximum at the highest tracked level ``<= level`` for a resource, or
    None when the resource has no count ladder at or below that level. Pure DB read."""
    row = access.db.one(
        "SELECT count FROM class_resource_level WHERE resource_id=? AND level<=? AND count IS NOT NULL "
        "ORDER BY level DESC LIMIT 1", resource_id, level)
    return row["count"] if row is not None else None


def grant_resources(access: ValidatorAccess, owner_kind: str, owner_id: str,
                    at_level: int | None = None) -> list[dict]:
    """The ``grant_resource`` use-pools an owner confers, as
    ``{id, name, uses_kind, uses_num, uses_ability_id}``. ``uses_kind`` says HOW the maximum is
    determined (a fixed integer, the proficiency bonus, or an ability modifier); the raw fields are
    returned unchanged so the consumer computes the maximum itself. Pure DB read via the grant spine
    (optionally level-gated: a NULL ``gained_at_level`` always applies)."""
    out: list[dict] = []
    for h in primitives.grants_for(access.db, "grant_resource", owner_kind, owner_id, at_level):
        out.append({
            "id": h["id"],
            "name": h["name"],
            "uses_kind": h["uses_kind"],
            "uses_num": h["uses_num"],
            "uses_ability_id": h["uses_ability_id"],
        })
    return out


def owned_resource_names(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list[str]:
    """Every resource NAME an owner confers — both ``class_resource`` rows (a count-ladder pool AND a
    die-/bonus-valued pool with no count ladder) and ``grant_resource`` use-pools — regardless of the
    level gate. This is the name-existence set for the orphan check: a budget key naming any of these
    denotes a resource the build owns (even one whose maximum is not queryable, e.g. a die pool, or
    one not yet reached at the build's level), so it is not an orphan. Pure DB read."""
    names = [r["name"] for r in access.db.q(
        "SELECT name FROM class_resource WHERE owner_kind=? AND owner_id=?", owner_kind, owner_id)]
    names += [h["name"] for h in
              primitives.grants_for(access.db, "grant_resource", owner_kind, owner_id)]
    return names


def ability_abbrev(access: ValidatorAccess, ability_id: str) -> str | None:
    """The lower-cased short abbreviation of an ability (the key CORE uses for it), or None."""
    abbr = access.db.scalar("SELECT abbrev FROM ability WHERE id=?", ability_id)
    return abbr.lower() if abbr else None
