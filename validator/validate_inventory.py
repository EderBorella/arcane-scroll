"""Inventory validation adapter — passes INVENTORY (and optional MODIFIER for C-I1e) to the
inventory check module. No path translation needed: the check produces paths directly into the
inventory:1 shape."""
from validator.checks import inventory
from validator.report import Violation, build_report


def validate_inventory(core: dict, inventory_sheet: dict,
                       modifier: dict | None, access) -> dict:
    merged = {
        "equipped": inventory_sheet.get("equipped"),
        "backpack": inventory_sheet.get("backpack", []),
        "modifier": modifier,
    }
    try:
        violations = inventory.check(merged, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="inventory",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
