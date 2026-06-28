"""Normalize and validate an incoming request into a character Spec (validated against the catalog)."""
from dataclasses import dataclass, field

from app.generation.helpers import _ci, _norm


@dataclass
class Spec:
    race: str
    classes: list                       # [(class_index, level)]
    subclasses: dict = field(default_factory=dict)   # class_index -> subclass override
    unique: str | None = None           # the UI "what is unique about this character?" field


def parse(cat, payload: dict) -> Spec:
    """payload: {race, classes:[{class, level}], subclasses?:{class:name}, unique?:str}."""
    race = str(payload.get("race", "")).strip()
    if _norm(race) not in {_norm(r) for r in cat.get("valid_races", [])}:
        raise ValueError(f"unknown race: {race!r}")

    classes_in = payload.get("classes") or []
    if not classes_in:
        raise ValueError("at least one class is required")
    classes = []
    for c in classes_in:
        ci, lv = _ci(c["class"]), int(c["level"])
        if not cat.record("classes", ci):
            raise ValueError(f"unknown class: {c['class']!r}")
        if not 1 <= lv <= 20:
            raise ValueError(f"level out of range: {lv}")
        classes.append((ci, lv))

    return Spec(race=race, classes=classes,
                subclasses=payload.get("subclasses") or {}, unique=payload.get("unique"))
