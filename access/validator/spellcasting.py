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


def subclass_cantrips_prepared(access: ValidatorAccess, subclass_id: str,
                              class_level: int) -> tuple[int | None, int | None]:
    """(cantrips_known, prepared_spells) for a third-caster subclass at a class level."""
    row = access.db.one(
        "SELECT cantrips_known, prepared_spells FROM subclass_cantrips_prepared "
        "WHERE subclass_id=? AND class_level=?", subclass_id, class_level)
    if row is None:
        return None, None
    return row["cantrips_known"], row["prepared_spells"]


def subclass_is_third_caster(access: ValidatorAccess, subclass_id: str) -> bool:
    """True if a subclass grants third-caster spellcasting (Eldritch Knight / Arcane Trickster-style)."""
    return access.db.one(
        "SELECT 1 FROM subclass_spellcasting WHERE subclass_id=?", subclass_id) is not None


def subclass_caster_list(access: ValidatorAccess, subclass_id: str) -> str | None:
    """The class id whose spell list a third-caster subclass casts from (e.g. Eldritch Knight ->
    wizard), or None if the subclass has no third-caster spellcasting row of its own."""
    return access.db.scalar(
        "SELECT spell_list_class_id FROM subclass_spellcasting WHERE subclass_id=?", subclass_id)


def subclass_slots(access: ValidatorAccess, subclass_id: str, class_level: int) -> dict[int, int]:
    """{slot_level: slot_count} for a third-caster subclass at a given class level."""
    return {row["slot_level"]: row["slot_count"] for row in access.db.q(
        "SELECT slot_level, slot_count FROM subclass_spell_slot WHERE subclass_id=? AND class_level=?",
        subclass_id, class_level)}


def spell_on_class_list(access: ValidatorAccess, spell_id: str, class_id: str) -> bool:
    """True if a spell is on a class's spell list."""
    return access.db.one(
        "SELECT 1 FROM spell_class WHERE spell_id=? AND class_id=?", spell_id, class_id) is not None


def list_widening_classes(access: ValidatorAccess, owner_kind: str, owner_id: str,
                         at_level: int | None = None) -> list[str]:
    """Class ids whose spell list is ADDITIONALLY legal for an owner at `at_level`, via a
    Magical-Secrets-style grant: a grant_spell row gained at or below `at_level` that carries a
    grant_spell_choice with from_kind='class_list' -- the widened list ids live in that grant's
    grant_spell_choice_value.value_id rows. DB fact: Bard's Magical Secrets (row l10-gsp-0010) is a
    grant_spell(class, bard, gained_at_level=10) + grant_spell_choice(from_kind='class_list')
    widening to {bard, cleric, druid, wizard}."""
    widened: set[str] = set()
    for header in primitives.grants_for(access.db, "grant_spell", owner_kind, owner_id, at_level):
        children = primitives.children_of(access.db, "grant_spell", header["id"])
        choices = children.get("grant_spell_choice", [])
        if not any(c["from_kind"] == "class_list" for c in choices):
            continue
        for row in children.get("grant_spell_choice_value", []):
            widened.add(row["value_id"])
    return sorted(widened)


def granted_spell_ids(access: ValidatorAccess, owner_kind: str, owner_id: str) -> set[str]:
    """spell_ids always granted to an owner (species/feat/subclass/class), via the grant_spell ->
    grant_spell_fixed spine. These are additive and may legitimately sit off the owner's class list."""
    ids: set[str] = set()
    for header in primitives.grants_for(access.db, "grant_spell", owner_kind, owner_id):
        children = primitives.children_of(access.db, "grant_spell", header["id"])
        for row in children.get("grant_spell_fixed", []):
            ids.add(row["spell_id"])
    return ids


def class_list_spell_choices(access: ValidatorAccess, owner_kind: str,
                             owner_id: str) -> list[dict]:
    """Return class_list-choice grants for an owner.

    Each result: {class_list_ids: [str], spell_level_min: int|None, spell_level_max: int|None,
                  choose_n: int|None}
    """
    results: list[dict] = []
    for header in primitives.grants_for(access.db, "grant_spell", owner_kind, owner_id):
        children = primitives.children_of(access.db, "grant_spell", header["id"])
        for ch in children.get("grant_spell_choice", []):
            if ch["from_kind"] != "class_list":
                continue
            value_ids = [r["value_id"] for r in children.get("grant_spell_choice_value", [])]
            if not value_ids:
                continue
            results.append({
                "class_list_ids": value_ids,
                "spell_level_min": ch["spell_level_min"],
                "spell_level_max": ch["spell_level_max"],
                "choose_n": ch["choose_n"],
            })
    return results
