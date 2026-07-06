"""The validator's finding model and aggregated report.

A run collects `Violation`s and folds them into `{legal, complete, violations[], summary}`:
`legal` = no illegal findings; `complete` = nothing expected-but-missing. An `internal` finding (a
check errored) makes the run neither legal nor complete, because a crashed check cannot certify
the sheet."""
from dataclasses import dataclass


@dataclass
class Violation:
    domain: str
    code: str
    kind: str            # "illegal" | "incomplete" | "internal"
    message: str
    path: str | None = None

    @property
    def severity(self) -> str:
        return "ERROR" if self.kind == "illegal" else "WARNING"


def build_report(violations: list[Violation]) -> dict:
    vs = sorted(violations, key=lambda v: (v.domain, v.code))
    errors = sum(1 for v in vs if v.kind == "illegal")
    return {
        "legal": not any(v.kind in ("illegal", "internal") for v in vs),
        "complete": not any(v.kind in ("incomplete", "internal") for v in vs),
        "violations": [
            {"domain": v.domain, "code": v.code, "severity": v.severity,
             "message": v.message, "path": v.path}
            for v in vs
        ],
        "summary": {"total": len(vs), "errors": errors, "warnings": len(vs) - errors},
    }
