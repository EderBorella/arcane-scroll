"""Orchestrator. Runs every registered check, aggregates all findings, and returns one organized
report. A check that raises does NOT stop the run — it's recorded as an `internal` finding and the
remaining checks still run, so every error surfaces at once (that's the whole point)."""
from collections import Counter

from validator.checks import ability_scores, class_level, spellcasting
from validator.report import ERROR, INTERNAL, WARNING, Violation

DEFAULT_CHECKS = [class_level.check, ability_scores.check, spellcasting.check]


def validate(sheet, rules, checks=None):
    violations = []
    for chk in (checks if checks is not None else DEFAULT_CHECKS):
        try:
            violations.extend(chk(sheet, rules) or [])
        except Exception as e:                       # a buggy check must never abort the whole validation
            layer = getattr(chk, "__module__", "?").rsplit(".", 1)[-1]
            violations.append(Violation(layer, "check_crashed",
                                        f"validator check raised {type(e).__name__}: {e}",
                                        severity=INTERNAL))

    violations.sort(key=lambda v: (v.layer, v.code))        # organized: grouped by layer, then code
    by_sev = Counter(v.severity for v in violations)
    return {
        "legal": by_sev.get(ERROR, 0) == 0,
        "complete": by_sev.get(INTERNAL, 0) == 0,           # False if any check crashed → partial validation
        "violations": [v.as_dict() for v in violations],
        "summary": {
            "errors": by_sev.get(ERROR, 0),
            "warnings": by_sev.get(WARNING, 0),
            "internal": by_sev.get(INTERNAL, 0),
            "by_layer": dict(Counter(v.layer for v in violations)),
        },
    }
