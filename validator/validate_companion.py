"""COMPANION validation adapter — passes CORE and the companion sheet as separate
top-level keys. No merge: the check reads each key directly. For the concrete
slice no owner context (cast level / owner stats) is needed — that is only for
the templated-companion scaling path (P2)."""
from validator.checks import companion
from validator.report import Violation, build_report


def validate_companion(core: dict, companion_sheet: dict, access) -> dict:
    merged = {
        "core": core or {},
        "companion": companion_sheet,
    }
    try:
        violations = companion.check(merged, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="companion",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
