"""MODIFIER validation adapter — passes CORE, INVENTORY, GRIMOIRE, and MODIFIER as separate
top-level keys. No merge — the check module reads each key directly. Pattern differs from
grimoire/inventory (which merge) because the orchestrator owns the flow here."""
from validator.checks import modifier
from validator.report import Violation, build_report


def validate_modifier(core: dict, inventory: dict | None, grimoire: dict | None,
                      modifier_sheet: dict, access) -> dict:
    merged = {
        "core": core,
        "inventory": inventory or {},
        "grimoire": grimoire or {},
        "modifier": modifier_sheet,
    }
    try:
        violations = modifier.check(merged, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="modifier",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
