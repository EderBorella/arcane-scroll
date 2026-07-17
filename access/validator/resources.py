"""Resources domain: the class-resource ladder (per-level use counts of class/subclass resources).

Pure DB facts — the per-level maximum is looked up here; the rule of which resources become a
sheet ``resource_budgets`` entry, and the cross-check of a declared maximum, live in the consumer."""
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
