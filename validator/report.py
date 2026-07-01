"""Structured, aggregatable validation findings. A check returns a list of these; nothing raises to
stop the run — the orchestrator (validate.py) collects everything and returns it at once."""
from dataclasses import asdict, dataclass

ERROR = "error"        # the sheet is illegal
WARNING = "warning"    # advisory; doesn't make the sheet illegal
INTERNAL = "internal"  # a check itself failed — validation was incomplete, not a sheet problem


@dataclass
class Violation:
    layer: str             # which validation layer raised it (e.g. "class_level")
    code: str              # stable machine-readable code (e.g. "subclass_too_early")
    message: str           # meaningful, human-readable explanation
    expected: object = None
    actual: object = None
    severity: str = ERROR

    def as_dict(self):
        return asdict(self)
