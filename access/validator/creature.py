"""Creature-domain DB facts: statblock rows for a creature and the owner->creature
companion linkage.

Pure DB reads — no rule math.  Every function returns raw rows (or a small dict of
raw-row lists), exactly as stored.  Deriving a companion's effective statblock
(scaling a templated block by spell level, summing formula terms, applying owner
stats) is a future deriver/validator concern and does NOT live here.

The creature catalog carries a creature and its child facts across several tables
(abilities, speeds, senses, skills, defences, traits/actions, and typed formulas).
``grant_companion`` is the linkage spine: it maps an owner (a spell, a subclass, a
magic item, ...) to a creature it confers as a companion, level-gated the same way
the other grant readers gate by ``gained_at_level``.
"""
from access.validator import ValidatorAccess


def creature_row(access: ValidatorAccess, creature_id: str):
    """The header row of a creature (identity, size, type, AC/HP facts, CR), or None."""
    return access.db.one("SELECT * FROM creature WHERE id=?", creature_id)


def creature_abilities(access: ValidatorAccess, creature_id: str) -> list:
    """Raw ability-score rows for a creature (creature_ability)."""
    return access.db.q(
        "SELECT ability_id, score FROM creature_ability WHERE creature_id=? "
        "ORDER BY ability_id", creature_id)


def creature_speeds(access: ValidatorAccess, creature_id: str) -> list:
    """Raw movement rows for a creature (creature_speed); feet XOR formula_note."""
    return access.db.q(
        "SELECT movement_mode_id, feet, formula_note FROM creature_speed "
        "WHERE creature_id=? ORDER BY movement_mode_id", creature_id)


def creature_senses(access: ValidatorAccess, creature_id: str) -> list:
    """Raw sense rows for a creature (creature_sense)."""
    return access.db.q(
        "SELECT sense_id, range_ft FROM creature_sense WHERE creature_id=? "
        "ORDER BY sense_id", creature_id)


def creature_skills(access: ValidatorAccess, creature_id: str) -> list:
    """Raw skill-bonus rows for a creature (creature_skill)."""
    return access.db.q(
        "SELECT skill_id, bonus FROM creature_skill WHERE creature_id=? "
        "ORDER BY skill_id", creature_id)


def creature_passive_perception(access: ValidatorAccess, creature_id: str) -> int | None:
    """The stated passive Perception of a creature, or None if none is stored."""
    return access.db.scalar(
        "SELECT value FROM creature_passive_perception WHERE creature_id=?", creature_id)


def creature_defenses(access: ValidatorAccess, creature_id: str) -> dict:
    """A creature's defence facts split by kind:

        {
          "resistance":          [creature_resistance rows],
          "immunity_damage":     [creature_immunity rows with a damage_type_id],
          "immunity_condition":  [creature_immunity rows with a condition_id],
          "vulnerability":       [creature_vulnerability rows],
        }

    ``creature_immunity`` is CHECK-constrained to carry a damage type XOR a
    condition; the split just reflects which column is populated (no rule math).
    """
    resistance = access.db.q(
        "SELECT damage_type_id, note FROM creature_resistance WHERE creature_id=? "
        "ORDER BY damage_type_id", creature_id)
    immunity_damage = access.db.q(
        "SELECT damage_type_id, note FROM creature_immunity "
        "WHERE creature_id=? AND damage_type_id IS NOT NULL ORDER BY damage_type_id",
        creature_id)
    immunity_condition = access.db.q(
        "SELECT condition_id, note FROM creature_immunity "
        "WHERE creature_id=? AND condition_id IS NOT NULL ORDER BY condition_id",
        creature_id)
    vulnerability = access.db.q(
        "SELECT damage_type_id FROM creature_vulnerability WHERE creature_id=? "
        "ORDER BY damage_type_id", creature_id)
    return {
        "resistance": resistance,
        "immunity_damage": immunity_damage,
        "immunity_condition": immunity_condition,
        "vulnerability": vulnerability,
    }


def creature_traits(access: ValidatorAccess, creature_id: str) -> list:
    """Raw trait rows for a creature (creature_trait.kind='trait')."""
    return access.db.q(
        "SELECT * FROM creature_trait WHERE creature_id=? AND kind='trait' "
        "ORDER BY id", creature_id)


def creature_actions(access: ValidatorAccess, creature_id: str) -> list:
    """Raw action rows for a creature (creature_trait.kind in action/bonus_action/reaction)."""
    return access.db.q(
        "SELECT * FROM creature_trait WHERE creature_id=? "
        "AND kind IN ('action','bonus_action','reaction') ORDER BY id", creature_id)


def creature_trait_by_id(access: ValidatorAccess, trait_id: str):
    """The single creature_trait row with this id (any kind), or None."""
    return access.db.one("SELECT * FROM creature_trait WHERE id=?", trait_id)


def creature_formulas(access: ValidatorAccess, creature_id: str) -> list:
    """Raw typed-formula header rows for a creature (creature_formula)."""
    return access.db.q(
        "SELECT * FROM creature_formula WHERE creature_id=? ORDER BY id", creature_id)


def creature_formula_terms(access: ValidatorAccess, formula_id: str) -> list:
    """Raw term rows of one creature formula (creature_formula_term)."""
    return access.db.q(
        "SELECT coefficient, variable, above_level FROM creature_formula_term "
        "WHERE formula_id=? ORDER BY variable", formula_id)


def companion_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                     at_level: int | None = None) -> list:
    """Raw grant_companion rows for an owner, optionally level-gated.

    A NULL gained_at_level means "always" (not level-gated), so it is kept for any
    ``at_level``, mirroring the other grant readers.
    """
    sql = ("SELECT id, owner_kind, owner_id, creature_id, gained_at_level, "
           "duration_amount, duration_unit_id, at_spell_level, notes "
           "FROM grant_companion WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    sql += " ORDER BY id"
    return access.db.q(sql, *params)


def companion_grants_for_creature(access: ValidatorAccess, creature_id: str) -> list:
    """Raw grant_companion rows that confer this creature, keyed from the creature
    side of the linkage (the reverse of :func:`companion_grants`). Used to resolve a
    companion's owner (a spell or a subclass) so the scaling context can be built."""
    return access.db.q(
        "SELECT id, owner_kind, owner_id, creature_id, gained_at_level, "
        "duration_amount, duration_unit_id, at_spell_level, notes "
        "FROM grant_companion WHERE creature_id=? ORDER BY id", creature_id)
