"""Standalone MONSTER validation adapter — owner-less. Takes a monster-sheet:1
document directly (no CORE, no owner GRIMOIRE). The check re-derives each concrete
field from the creature catalog independently and rejects any templated (owner-scaled)
creature that cannot stand alone."""
from validator.checks import monster
from validator.report import Violation, build_report


def validate_monster(monster_sheet: dict, access) -> dict:
    try:
        violations = monster.check(monster_sheet or {}, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="monster",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
