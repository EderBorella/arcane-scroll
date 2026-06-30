"""Normalize and validate an incoming request into a character Spec (validated against the catalog)."""
from dataclasses import dataclass, field

from app.generation.helpers import _ci, _norm, required_abilities


@dataclass
class Spec:
    race: str
    classes: list                       # [(class_index, level)]
    subclasses: dict = field(default_factory=dict)   # class_index -> subclass override
    unique: str | None = None           # the UI "what is unique about this character?" field
    roll_wealth: bool = False           # take rolled starting gold INSTEAD of the class equipment (RAW)
    background: str | None = None       # explicit background; else code picks one (variety spread)
    fighting_style: str | None = None   # explicit fighting style; else code picks one when granted


def parse(cat, payload: dict) -> Spec:
    """payload: {race, classes:[{class, level}], subclasses?:{class:name}, unique?:str,
    roll_starting_wealth?:bool}."""
    race = str(payload.get("race", "")).strip()
    # Validate case-insensitively, but store the catalog's canonical display name: downstream flavour
    # lookups (physical bounds, skin palette) are keyed by display name, so a request of "human" must
    # become "Human" or it silently falls back to generic bounds.
    canonical = next((r for r in cat.get("valid_races", []) if _norm(r) == _norm(race)), None)
    if canonical is None:
        raise ValueError(f"unknown race: {race!r}")
    race = canonical

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

    # multiclass legality: the standard array has only three 13+ slots
    if len(required_abilities(cat, [(ci, lv, None) for ci, lv in classes])) > 3:
        raise ValueError("illegal multiclass: requires 13+ in more than three abilities")

    bg = payload.get("background")
    if bg:                              # validate + canonicalise an explicit background to its display name
        bg = next((b for b in cat.get("backgrounds", []) if _norm(b) == _norm(bg)), None)
        if bg is None:
            raise ValueError(f"unknown background: {payload.get('background')!r}")

    return Spec(race=race, classes=classes,
                subclasses=payload.get("subclasses") or {}, unique=payload.get("unique"),
                roll_wealth=bool(payload.get("roll_starting_wealth", False)),
                background=bg, fighting_style=payload.get("fighting_style"))
