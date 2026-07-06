"""Saving-throws domain DB facts: which abilities a class grants saving-throw proficiency in, and
which abilities a feat/species grants via the proficiency grant spine (e.g. Resilient)."""
from access import primitives
from access.validator import ValidatorAccess


def class_save_abilities(access: ValidatorAccess, class_id: str) -> list[str]:
    """The ability ids a class grants saving-throw proficiency in, unordered."""
    return [row["ability_id"] for row in access.db.q(
        "SELECT ability_id FROM class_saving_throw WHERE class_id=?", class_id)]


def granted_save_abilities(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list[str]:
    """Ability ids an owner (feat, species, ...) grants saving-throw proficiency in via
    grant_proficiency(target_kind='saving_throw') rows, resolved through grant_proficiency_value."""
    out: list[str] = []
    for header in primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id):
        if header["target_kind"] != "saving_throw":
            continue
        out.extend(row["target_id"] for row in
                   primitives.children_of(access.db, "grant_proficiency", header["id"])
                   .get("grant_proficiency_value", []))
    return out
