"""Parse an incoming generation request into a validated build spec — a *species*,
one or more class+level entries (with optional subclass overrides), and an optional background. Every
identifier is validated against the loaded ruleset via the generator data-access layer, so an unknown
id fails fast here rather than reaching the grammar. Content-neutral: the option set is the DAL's.
"""
from dataclasses import dataclass, field

from access.generator import backgrounds as bg_q
from access.generator import classes as class_q
from access.generator import species as species_q


@dataclass
class RequestSpec:
    species: str                       # species id
    classes: list                      # [(class_id, level), ...]
    subclasses: dict = field(default_factory=dict)   # class_id -> subclass_id override
    background: str | None = None      # background id, or None to let the grammar pick one
    character_id: str | None = None
    character_name: str | None = None
    alignment: str | None = None       # optional alignment id


def _ids(rows):
    return {r["id"] for r in rows}


def parse_request(access, payload: dict) -> RequestSpec:
    """Validate and normalise a request payload::

        {species, classes:[{class, level}], subclasses?:{class:subclass}, background?,
         character_id?, character_name?, alignment?}

    into a :class:`RequestSpec`. Raises ``ValueError`` for an unknown species/class/subclass/
    background id or an out-of-range level."""
    species = str(payload.get("species", "")).strip()
    if species not in _ids(species_q.list_species(access)):
        raise ValueError(f"unknown species: {species!r}")

    class_ids = _ids(class_q.list_classes(access))
    classes_in = payload.get("classes") or []
    if not classes_in:
        raise ValueError("at least one class is required")
    classes = []
    for c in classes_in:
        cid = str(c.get("class", "")).strip()
        if cid not in class_ids:
            raise ValueError(f"unknown class: {cid!r}")
        level = int(c.get("level", 0))
        if not 1 <= level <= 20:
            raise ValueError(f"level out of range: {level}")
        classes.append((cid, level))

    subclasses = {}
    for cid, sub in (payload.get("subclasses") or {}).items():
        valid = _ids(class_q.subclasses_for_class(access, cid))
        if sub not in valid:
            raise ValueError(f"unknown subclass {sub!r} for class {cid!r}")
        subclasses[cid] = sub

    background = payload.get("background")
    if background is not None and background not in _ids(bg_q.list_backgrounds(access)):
        raise ValueError(f"unknown background: {background!r}")

    return RequestSpec(
        species=species, classes=classes, subclasses=subclasses, background=background,
        character_id=payload.get("character_id"), character_name=payload.get("character_name"),
        alignment=payload.get("alignment"))
