"""Equipment-derived sheet fields. For now: detect the equipped armour (for armour-based AC) from the
chosen equipment + the fixed class package. Full inventory assembly + treasure are the next phases.

The model picks equipment as route labels + `_pick` companions; the class also grants fixed items
(e.g. paladin Chain Mail, ranger Longbow) that aren't in the choices. We scan all of it for an armour
item and resolve its stats from the equipment records."""
from app.generation import helpers as H

_ARMOUR_CATS = {"Light", "Medium", "Heavy"}


def _carried_text(cat, choices) -> str:
    """Lower-cased blob of every equipment item the character has — chosen routes + `_pick` companions
    + the fixed class starting package."""
    parts = []
    for k, v in choices.items():
        if k.startswith("equipment"):
            parts += v if isinstance(v, list) else [str(v)]
    for c in choices.get("classes", []):
        rec = cat.record("classes", H._ci(c["class"])) or {}
        parts += [e.get("equipment", {}).get("name", "") for e in rec.get("starting_equipment", [])]
    return " | ".join(parts).lower()


def equipped_armour(cat, choices):
    """(armour_record, has_shield) — the highest-base armour the character carries (None if unarmoured)."""
    blob = _carried_text(cat, choices)
    best = None
    for e in cat.records("equipment").values():
        if e.get("armor_category") in _ARMOUR_CATS and e["name"].lower() in blob:
            if best is None or e["armor_class"]["base"] > best["armor_class"]["base"]:
                best = e
    return best, "shield" in blob
