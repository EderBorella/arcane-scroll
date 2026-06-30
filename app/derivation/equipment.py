"""Equipment-derived sheet fields. For now: detect the equipped armour (for armour-based AC) from the
chosen equipment + the fixed class package. Full inventory assembly + treasure are the next phases.

The model picks equipment as route labels + `_pick` companions; the class also grants fixed items
(e.g. paladin Chain Mail, ranger Longbow) that aren't in the choices. We scan all of it for an armour
item and resolve its stats from the equipment records."""
import re

from app.generation import helpers as H

_ARMOUR_CATS = {"Light", "Medium", "Heavy"}


def _carries_shield(cat, blob: str) -> bool:
    """Whether a shield is carried. Matches a Shield-category record name as a whole word, so
    'a shielded lantern' doesn't register a shield the way a naked `"shield" in blob` would."""
    for e in cat.records("equipment").values():
        if e.get("armor_category") == "Shield" and re.search(rf"\b{re.escape(e['name'].lower())}\b", blob):
            return True
    return False


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
    """(armour_record, has_shield) — the armour the character wears (None if unarmoured).

    Names are matched as substrings of the carried-equipment blob. Some armour names are sub-phrases
    of a more specific one ("Plate Armor" ⊂ "Half Plate Armor", "Leather Armor" ⊂ "Studded Leather
    Armor"), so a less-specific name can match purely because the specific one is present. We drop any
    matched name contained in another matched name, then take the highest-base survivor."""
    blob = _carried_text(cat, choices)
    matched = [e for e in cat.records("equipment").values()
               if e.get("armor_category") in _ARMOUR_CATS and e["name"].lower() in blob]
    names = {e["name"].lower() for e in matched}
    specific = [e for e in matched
                if not any(e["name"].lower() != n and e["name"].lower() in n for n in names)]
    best = max(specific, key=lambda e: e["armor_class"]["base"], default=None)
    return best, _carries_shield(cat, blob)
