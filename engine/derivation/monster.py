"""Standalone MONSTER materialization — owner-less concrete-creature sheets.

A materialised monster is a STANDALONE stat block: a concrete catalogued creature
emitted in the companion-modifier statblock shape, but with NO owner. It reuses the
concrete companion field derivation (:func:`engine.derivation.companion.derive_concrete`)
wholesale — a standalone monster is essentially a concrete companion with no owner —
and adds only the owner-less framing (a top-level ``creature_id`` per monster and a
``monsters[]`` sheet), producing a ``monster-sheet:1`` document.

TEMPLATED creatures (those carrying ``creature_formula`` rows) CANNOT be materialised
standalone: their stats only exist relative to an owner's cast level / owner stats, so
there is no owner context to scale them. Requesting one raises
:class:`MonsterMaterializationError` — it is rejected, never emitted with un-scaled
zeros. Arbitrary-monster breadth beyond the catalogued creatures is a separate concern.
"""
from engine.derivation import companion as comp
from access.validator import creature as creature_q


class MonsterMaterializationError(ValueError):
    """Raised when a creature cannot be materialised as a standalone monster:
    it is not in the catalogue, or it is templated (owner-scaled) and so has no
    stand-alone stat block."""


def derive_monster(access, creature_id: str) -> dict:
    """Materialise ONE concrete creature as a standalone monster entry
    ``{"creature_id": ..., "stat_block": <shared base stat block>}``.

    Raises :class:`MonsterMaterializationError` when the creature id does not
    resolve or the creature is templated (owner-scaled)."""
    row = creature_q.creature_row(access, creature_id)
    if row is None:
        raise MonsterMaterializationError(
            f"creature {creature_id!r} is not in the catalogue")
    if comp.is_templated(access, creature_id):
        raise MonsterMaterializationError(
            f"creature {creature_id!r} is owner-scaled (templated) and cannot be "
            f"materialised as a standalone monster: its stats only exist relative "
            f"to an owner's cast level")
    # The owner-less monster references the SHARED base stat block (no companion_index):
    # derive_concrete emits the bare base when no owner-linkage index is supplied.
    stat_block = comp.derive_concrete(access, creature_id, row)
    return {"creature_id": creature_id, "stat_block": stat_block}


def derive_monster_sheet(access, creature_ids) -> dict:
    """Materialise a ``monster-sheet:1`` document from an ordered list of concrete
    creature ids. Each entry's stat block is the shared owner-agnostic base — no
    ``companion_index``; a monster's position is simply its index in ``monsters[]``
    (there is no owner to link back to). Any templated or unknown creature id raises
    :class:`MonsterMaterializationError` (fail-fast rejection — a standalone sheet
    must never carry an un-scaled templated block)."""
    monsters = [derive_monster(access, creature_id) for creature_id in (creature_ids or [])]
    return {"schema_version": 1, "monsters": monsters}
