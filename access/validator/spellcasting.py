"""Spellcasting-domain DB facts: caster progression, slot tables (single-class, multiclass, pact),
per-class cantrip/prepared counts, third-caster subclass slots, and spell-list membership (including
the always-granted-spell spine). No rule math here -- combined-caster-level rounding and the
count/slot comparisons live in the check."""
from access import primitives
from access.validator import ValidatorAccess


def caster_progression(access: ValidatorAccess, class_id: str) -> str | None:
    """A class's caster_progression ('none'|'full'|'half'|'pact'), or None if the class is unknown."""
    return access.db.scalar("SELECT caster_progression FROM class WHERE id=?", class_id)


def class_slots(access: ValidatorAccess, class_id: str, class_level: int) -> dict[int, int]:
    """{slot_level: slot_count} for a single-class caster at a given class level."""
    return {row["slot_level"]: row["slot_count"] for row in access.db.q(
        "SELECT slot_level, slot_count FROM class_spell_slot WHERE class_id=? AND class_level=?",
        class_id, class_level)}


def multiclass_slots(access: ValidatorAccess, caster_level: int) -> dict[int, int]:
    """{slot_level: slot_count} for a combined multiclass caster level."""
    return {row["slot_level"]: row["slot_count"] for row in access.db.q(
        "SELECT slot_level, slot_count FROM multiclass_slot WHERE caster_level=?", caster_level)}


def pact_slots(access: ValidatorAccess, class_id: str, class_level: int) -> dict[int, int]:
    """{slot_level: slot_count} for pact magic (always separate from other slots)."""
    return {row["slot_level"]: row["slot_count"] for row in access.db.q(
        "SELECT slot_level, slot_count FROM pact_slot WHERE class_id=? AND class_level=?",
        class_id, class_level)}


def cantrips_prepared(access: ValidatorAccess, class_id: str, level: int) -> tuple[int | None, int | None]:
    """(cantrips_known, prepared_spells) for a class at a level, or (None, None) if not tabulated."""
    row = access.db.one(
        "SELECT cantrips_known, prepared_spells FROM class_cantrips_prepared WHERE class_id=? AND level=?",
        class_id, level)
    if row is None:
        return None, None
    return row["cantrips_known"], row["prepared_spells"]


def subclass_is_third_caster(access: ValidatorAccess, subclass_id: str) -> bool:
    """True if a subclass grants third-caster spellcasting (Eldritch Knight / Arcane Trickster-style)."""
    return access.db.one(
        "SELECT 1 FROM subclass_spellcasting WHERE subclass_id=?", subclass_id) is not None


def subclass_slots(access: ValidatorAccess, subclass_id: str, class_level: int) -> dict[int, int]:
    """{slot_level: slot_count} for a third-caster subclass at a given class level."""
    return {row["slot_level"]: row["slot_count"] for row in access.db.q(
        "SELECT slot_level, slot_count FROM subclass_spell_slot WHERE subclass_id=? AND class_level=?",
        subclass_id, class_level)}


def spell_on_class_list(access: ValidatorAccess, spell_id: str, class_id: str) -> bool:
    """True if a spell is on a class's spell list."""
    return access.db.one(
        "SELECT 1 FROM spell_class WHERE spell_id=? AND class_id=?", spell_id, class_id) is not None


def granted_spell_ids(access: ValidatorAccess, owner_kind: str, owner_id: str) -> set[str]:
    """spell_ids always granted to an owner (species/feat/subclass/class), via the grant_spell ->
    grant_spell_fixed spine. These are additive and may legitimately sit off the owner's class list."""
    ids: set[str] = set()
    for header in primitives.grants_for(access.db, "grant_spell", owner_kind, owner_id):
        children = primitives.children_of(access.db, "grant_spell", header["id"])
        for row in children.get("grant_spell_fixed", []):
            ids.add(row["spell_id"])
    return ids
