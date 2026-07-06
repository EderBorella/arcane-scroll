"""Resilient orchestrator: run every registered check, aggregate all findings into one report. A check
that raises becomes a single `internal` finding and never aborts the run."""
from validator.checks import ALL_CHECKS as _REGISTRY
from validator.report import Violation, build_report

ALL_CHECKS = _REGISTRY


def validate(sheet: dict, access) -> dict:
    violations: list[Violation] = []
    for check in ALL_CHECKS:
        try:
            violations.extend(check(sheet, access) or [])
        except Exception as e:  # noqa: BLE001 — resilience is the point
            name = getattr(check, "__module__", "?").rsplit(".", 1)[-1]
            violations.append(Violation("internal", f"check-raised:{name}", "internal",
                                        f"check raised {type(e).__name__}: {e}"))
    return build_report(violations)
