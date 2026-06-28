"""Vitals & movement — hit points, hit dice, armour class (unarmoured), and speed.

Armour AC from equipped items is deferred (no item-stat records yet), so AC is the unarmoured value,
taking the best of Barbarian (+CON) / Monk (+WIS) unarmoured defence."""
import re

from app.derivation.abilities import modifier


def max_hp(cat, classes, con_mod) -> int:
    """Max at the very first level (primary class), fixed average (die/2+1) per level after, +CON each."""
    hp, first = 0, True
    for ci, lv in classes:
        die = cat.record("classes", ci).get("hit_die", 8)
        for _ in range(lv):
            hp += (die if first else die // 2 + 1) + con_mod
            first = False
    return max(hp, 1)


def hit_dice(cat, classes) -> dict:
    """{'d10': 5, …} — pooled by die size across classes."""
    out = {}
    for ci, lv in classes:
        die = f"d{cat.record('classes', ci).get('hit_die', 8)}"
        out[die] = out.get(die, 0) + lv
    return out


def armor_class(cat, scores, classes) -> int:
    dex = modifier(scores["dex"])
    ac = 10 + dex
    cis = {ci for ci, _ in classes}
    if "barbarian" in cis:
        ac = max(ac, 10 + dex + modifier(scores["con"]))
    if "monk" in cis:
        ac = max(ac, 10 + dex + modifier(scores["wis"]))
    return ac


def speed(cat, race) -> int:
    """Race (or subrace → parent race) walking speed, with a generic fallback."""
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    sub = cat.record("subraces", idx)
    if sub:
        parent = cat.record("races", sub.get("race", {}).get("index"))
        return (parent or {}).get("speed", 30)
    return (cat.record("races", idx) or {}).get("speed", 30)
