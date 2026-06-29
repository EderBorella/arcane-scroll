"""Vitals & movement — hit points, hit dice, armour class, and speed.

AC is armour-based when armour is worn (base + Dex per the armour's rule), falling back to the
unarmoured value — the best of Barbarian (+CON) / Monk (+WIS) unarmoured defence."""
import re

from app.derivation.abilities import modifier


def max_hp(cat, classes, con_mod) -> int:
    """Max at the very first level (primary class), fixed average (die/2+1) per level after, +CON each."""
    hp, first = 0, True
    for ci, lv in classes:
        die = (cat.record("classes", ci) or {}).get("hit_die", 8)
        for _ in range(lv):
            hp += (die if first else die // 2 + 1) + con_mod
            first = False
    return max(hp, 1)


def hit_dice(cat, classes) -> dict:
    """{'d10': 5, …} — pooled by die size across classes."""
    out = {}
    for ci, lv in classes:
        die = f"d{(cat.record('classes', ci) or {}).get('hit_die', 8)}"
        out[die] = out.get(die, 0) + lv
    return out


def armor_class(scores, classes, armour=None, shield=False) -> int:
    """Worn-armour AC when armour is equipped (base + Dex per the armour's rule: light = full Dex,
    medium = +Dex capped at max_bonus, heavy = none); otherwise unarmoured (10 + Dex, taking the best
    of Barbarian +CON / Monk +WIS). +2 for a shield."""
    dex = modifier(scores["dex"])
    if armour:
        acd = armour["armor_class"]
        ac = acd["base"]
        if acd.get("dex_bonus"):
            if "max_bonus" in acd:
                ac += min(dex, acd["max_bonus"])
            elif armour.get("armor_category") == "Medium":
                ac += min(dex, 2)          # medium caps Dex at +2 even if the record omits max_bonus
            else:
                ac += dex                  # light armour: full Dex
    else:
        ac = 10 + dex
        cis = {ci for ci, _ in classes}
        if "barbarian" in cis:
            ac = max(ac, 10 + dex + modifier(scores["con"]))
        if "monk" in cis:
            ac = max(ac, 10 + dex + modifier(scores["wis"]))
    return ac + (2 if shield else 0)


def speed(cat, race) -> int:
    """Walking speed: a subrace's own speed if it sets one (e.g. Wood Elf 35), else its parent
    race's, else a base race's, with a generic fallback."""
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    sub = cat.record("subraces", idx)
    if sub:
        if "speed" in sub:
            return sub["speed"]
        parent = cat.record("races", sub.get("race", {}).get("index"))
        return (parent or {}).get("speed", 30)
    return (cat.record("races", idx) or {}).get("speed", 30)
