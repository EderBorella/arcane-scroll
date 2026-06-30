"""Equipment-derived sheet fields: a concrete inventory, the equipped armour (for armour-based AC), and
starting treasure (gold).

Assembly resolves the model's chosen routes — plus the fixed class package — into `[{item, quantity}]`
via the seed-built `class_equipment` relation. When the request set `roll_starting_wealth`, the
character takes gold INSTEAD of the class equipment (RAW): no inventory, unarmoured AC, and the treasure
is the rolled class starting wealth plus background gold. Otherwise treasure is the background gold."""
import random
import re

from app.generation import helpers as H

_ARMOUR_CATS = {"Light", "Medium", "Heavy"}


def _roll_dice(expr, rng) -> int:
    """Sum of an 'NdM' roll (e.g. '5d4'); 0 if unparseable."""
    try:
        n, sides = (int(x) for x in str(expr).lower().split("d"))
    except (ValueError, AttributeError):
        return 0
    return sum(rng.randint(1, sides) for _ in range(n))


def _background_gold(cat, name) -> int:
    """The chosen background's starting gold in gp (0 if none / not gp)."""
    if not name:
        return 0
    n = H._norm(name)
    bg = next((b for b in cat.records("backgrounds").values() if H._norm(b.get("name")) == n), None)
    sg = (bg or {}).get("starting_gold") or {}
    return sg.get("quantity", 0) if sg.get("unit", "gp") == "gp" else 0


def treasure(cat, choices, rng=random) -> dict:
    """Starting gold. Always the background's gold; plus the rolled class starting wealth (dice × x)
    when the character took gold instead of equipment (`roll_starting_wealth`)."""
    gp = _background_gold(cat, choices.get("background"))
    if choices.get("roll_starting_wealth"):
        sw = (cat.get("starting_wealth") or {}).get(_primary_index(choices))
        if sw:
            gp += _roll_dice(sw.get("dice", ""), rng) * sw.get("x", 1)
    return {"gp": gp}


def _primary_index(choices):
    classes = choices.get("classes") or []
    if not classes:
        return None
    c0 = classes[0]
    return H._ci(c0["class"] if isinstance(c0, dict) else (c0[0] if isinstance(c0, tuple) else c0))


def assemble_inventory(cat, choices) -> list:
    """Concrete `[{item, quantity}]` for the primary class — fixed package + the chosen routes/picks,
    resolved through the class_equipment relation. A category route's picks ride on the route object
    (`{route, weapons}`) already sized to that route, so there's nothing to trim."""
    if choices.get("roll_starting_wealth"):          # took gold instead of equipment → no class kit
        return []
    rel = (cat.get("class_equipment") or {}).get(_primary_index(choices))
    if not rel:
        return []
    items: dict[str, int] = {}

    def add(name, qty=1):
        if name:
            items[name] = items.get(name, 0) + qty

    for it in rel.get("fixed", []):
        add(it.get("item"), it.get("qty", 1))
    for slot in rel.get("slots", []):
        chosen = choices.get(slot["field"])
        if "category" in slot:                                   # direct category pick (concrete name)
            for nm in ([chosen] if isinstance(chosen, str) else list(chosen or [])):
                add(nm)
            continue
        # alternatives slot: a plain label (concrete routes) or a {route, weapons} object (category routes)
        if isinstance(chosen, dict):
            route, picks = chosen.get("route"), chosen.get("weapons") or []
        else:
            route, picks = chosen, []
        alt = next((a for a in slot.get("alternatives", []) if a["label"] == route), None)
        if not alt:
            continue
        for it in alt["items"]:
            add(it.get("item"), it.get("qty", 1))
        for nm in picks:
            add(nm)
    return [{"item": k, "quantity": v} for k, v in items.items()]


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
        if not k.startswith("equipment"):
            continue
        if isinstance(v, dict):                       # union route: {route, weapons}
            parts.append(str(v.get("route", "")))
            parts += [str(x) for x in (v.get("weapons") or [])]
        elif isinstance(v, list):
            parts += [str(x) for x in v]
        else:
            parts.append(str(v))
    for c in choices.get("classes", []):
        rec = cat.record("classes", H._ci(c["class"])) or {}
        parts += [e.get("equipment", {}).get("name", "") for e in rec.get("starting_equipment", [])]
    return " | ".join(parts).lower()


def equipped_armour(cat, choices):
    """(armour_record, has_shield) — the armour the character wears (None if unarmoured).
    Returns (None, False) when the character took gold instead of equipment.

    Names are matched as substrings of the carried-equipment blob. Some armour names are sub-phrases
    of a more specific one ("Plate Armor" ⊂ "Half Plate Armor", "Leather Armor" ⊂ "Studded Leather
    Armor"), so a less-specific name can match purely because the specific one is present. We drop any
    matched name contained in another matched name, then take the highest-base survivor."""
    if choices.get("roll_starting_wealth"):          # took gold instead of equipment → unarmoured
        return None, False
    blob = _carried_text(cat, choices)
    matched = [e for e in cat.records("equipment").values()
               if e.get("armor_category") in _ARMOUR_CATS and e["name"].lower() in blob]
    names = {e["name"].lower() for e in matched}
    specific = [e for e in matched
                if not any(e["name"].lower() != n and e["name"].lower() in n for n in names)]
    best = max(specific, key=lambda e: e["armor_class"]["base"], default=None)
    return best, _carries_shield(cat, blob)
