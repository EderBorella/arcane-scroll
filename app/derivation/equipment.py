"""Equipment-derived sheet fields: a concrete inventory, the equipped armour (for armour-based AC), and
starting treasure (gold).

Assembly resolves the model's chosen routes — plus the fixed class package — into `[{item, quantity}]`
via the seed-built `class_equipment` relation. When the request set `roll_starting_wealth`, the
character takes gold INSTEAD of the class equipment (RAW): no inventory, unarmoured AC, and the treasure
is the rolled class starting wealth plus background gold. Otherwise treasure is the background gold."""
import random

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


def equipped_armour(cat, inventory):
    """(armour_record, has_shield) from the assembled `inventory` — matched by EXACT item name against
    the equipment records (the highest-base worn armour, and whether any shield is carried). Because the
    inventory holds concrete catalog names, there's no substring/name-subset ambiguity. Unarmoured (and
    the gold-instead-of-equipment case, where the inventory is empty) yields (None, False)."""
    names = {i["item"] for i in inventory}
    best, shield = None, False
    for e in cat.records("equipment").values():
        if e["name"] not in names:
            continue
        category = e.get("armor_category")
        if category in _ARMOUR_CATS:
            if best is None or e["armor_class"]["base"] > best["armor_class"]["base"]:
                best = e
        elif category == "Shield":
            shield = True
    return best, shield
