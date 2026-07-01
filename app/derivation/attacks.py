"""Attacks — the sheet's weapon rows: for each weapon carried, its attack bonus and damage string.

Render-only (not a legality concern). The ability used is STR for melee, DEX for ranged, and the
better of the two for a finesse weapon; the proficiency bonus is added when the character is
proficient with the weapon — by category (Simple / Martial) or a specific-weapon proficiency read
straight from the class record (specific profs like "Rapiers" don't carry a category tag). Magic
bonuses aren't modelled yet — generated starting equipment is mundane."""
from app.generation import helpers as H


def _is_weapon(e) -> bool:
    return (e.get("equipment_category") or {}).get("index") == "weapon" or bool(e.get("weapon_category"))


def _name_match(prof, weapon) -> bool:
    """Loose singular/plural match of two _norm'd names ('rapiers' ~ 'rapier')."""
    return prof == weapon or prof.rstrip("s") == weapon or weapon.rstrip("s") == prof


def _proficiency(cat, ci):
    """(category set ⊆ {"simple","martial"}, [specific-weapon prof names]) from a class's proficiencies.
    Category comes from the reliable proficiency index ("simple-weapons"/"martial-weapons"); every other
    entry is kept as a specific name (armour/saves/tools simply never match a weapon, so they're inert)."""
    cats, specific = set(), []
    for p in (cat.record("classes", ci) or {}).get("proficiencies", []):
        idx = p.get("index", "")
        if idx in ("simple-weapons", "martial-weapons"):
            cats.add(idx.split("-", 1)[0])
        else:
            specific.append(p.get("name", ""))
    return cats, specific


def _proficient(weapon, cats, specific) -> bool:
    if H._norm(weapon.get("weapon_category", "")) in cats:
        return True
    w = H._norm(weapon.get("name", ""))
    return any(_name_match(H._norm(s), w) for s in specific)


def _ability(weapon, mods) -> str:
    props = {p.get("index") for p in weapon.get("properties", [])}
    if H._norm(weapon.get("weapon_range", "")) == "ranged":
        return "dex"
    if "finesse" in props:
        return "dex" if mods["dex"] >= mods["str"] else "str"
    return "str"


def _dice_str(dice, mod, dtype) -> str:
    sign = f"+{mod}" if mod > 0 else (str(mod) if mod < 0 else "")
    return f"{dice}{sign}" + (f" {dtype}" if dtype else "")


def _damage(weapon, mod) -> str:
    d = weapon.get("damage") or {}
    s = _dice_str(d.get("damage_dice", ""), mod, (d.get("damage_type") or {}).get("name", ""))
    th = weapon.get("two_handed_damage")                          # versatile: note the two-handed dice
    if th:
        s += f" (versatile {_dice_str(th.get('damage_dice', ''), mod, '')})"
    return s


def attack_rows(cat, mods, pb, classes, inventory) -> list:
    """`[{name, attack_bonus, damage}]` for each weapon in the assembled inventory (primary class's
    weapon proficiency decides whether the proficiency bonus applies)."""
    cats, specific = _proficiency(cat, classes[0][0])
    weapons = {e["name"]: e for e in cat.records("equipment").values() if _is_weapon(e)}
    rows = []
    for it in inventory:
        w = weapons.get(it["item"])
        if not w:
            continue
        ab = _ability(w, mods)
        bonus = mods[ab] + (pb if _proficient(w, cats, specific) else 0)
        rows.append({"name": w["name"], "attack_bonus": bonus, "damage": _damage(w, mods[ab])})
    return rows
