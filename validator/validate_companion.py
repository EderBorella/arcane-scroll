"""COMPANION validation adapter — passes CORE, the owner GRIMOIRE, and the companion
sheet as separate top-level keys. No merge: the check reads each key directly.
Concrete creatures ignore GRIMOIRE; templated (formula-scaled) creatures need it to
resolve the owner's spell attack modifier / spell save DC for independent
re-derivation of the scaled values."""
from validator.checks import companion
from validator.report import Violation, build_report


def validate_companion(core: dict, grimoire: dict | None, companion_sheet: dict, access) -> dict:
    merged = {
        "core": core or {},
        "grimoire": grimoire or {},
        "companion": companion_sheet,
    }
    try:
        violations = companion.check(merged, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="companion",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
