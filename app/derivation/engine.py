"""Derivation engine — compute a full character sheet from the model's (repaired) choices.

Pure: no model, no side-effects. Reads the catalog + the choices and resolves the numbers a sheet
needs — proficiency bonus, ability scores (incl. ASIs), modifiers, HP, AC, saving throws, the skill
table (with expertise), passive perception, initiative, speed, spell save DC / attack, and hit dice.

The model picked; this computes. `derive(cat, choices)` is the public entry; everything else is a
named pure helper over (catalog, scores, …) so each is unit-testable in isolation.

Deferred (data/scope, not oversight):
  * Armour AC from equipped items — there are no item-stat records yet, so AC is the *unarmoured*
    value, including Barbarian/Monk unarmoured defence.
  * Feat mechanical effects — only ASI bumps are applied; per-feat effects (e.g. Tough's HP) are
    their own body of work, as in the choice layer.
"""
import re

from app.generation import features
from app.generation import helpers as H


def _mod(score: int) -> int:
    return (score - 10) // 2


def _classes(choices) -> list:
    """[(class_index, level)] from the choices' class entries (class names are display-cased)."""
    return [(H._ci(c["class"]), c["level"]) for c in choices.get("classes", [])]


def proficiency_bonus(total_level: int) -> int:
    return 2 + (total_level - 1) // 4


# ── ability scores (base array + racial + ASIs) ───────────────────────────────
def _asi_bumps(choices, asi_label) -> tuple:
    """(ability indices bumped by ASI picks, number of feat-slot picks made)."""
    picks = choices.get("feat")
    picks = [picks] if isinstance(picks, str) else list(picks or [])
    by_name = {v.lower(): k for k, v in asi_label.items()}
    bumps = []
    for p in picks:
        pl = str(p).lower()
        if pl.startswith("ability score improvement"):
            bumps.append(next((ab for name, ab in by_name.items() if name in pl), None))
    return [b for b in bumps if b], len(picks)


def ability_scores(cat, choices) -> dict:
    """Base standard-array assignment + racial bonuses + ASIs (each pick +2, capped at 20)."""
    scores = {ab: v + H.race_bonus(cat, choices["race"], ab)
              for ab, v in choices["ability_assignment"].items()}
    classes = _classes(choices)
    total_slots = sum(features._asi_slots(cat, ci, lv) for ci, lv in classes)
    bumps, n_picks = _asi_bumps(choices, cat.get("asi_label", {}))
    reserved = max(0, total_slots - n_picks)        # 2+ slots reserve one code ASI on the primary ability
    primary = (cat.get("ability_priority", {}).get(classes[0][0]) or list(scores))[0]
    for ab in bumps + [primary] * reserved:
        scores[ab] = min(20, scores[ab] + 2)
    return scores


# ── hit points / hit dice ─────────────────────────────────────────────────────
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


# ── defences ──────────────────────────────────────────────────────────────────
def armor_class(cat, scores, classes) -> int:
    """Unarmoured AC (10 + DEX), taking the best of Barbarian (+CON) / Monk (+WIS) unarmoured defence.
    Armour from equipped items is deferred (no item-stat records)."""
    dex = _mod(scores["dex"])
    ac = 10 + dex
    cis = {ci for ci, _ in classes}
    if "barbarian" in cis:
        ac = max(ac, 10 + dex + _mod(scores["con"]))
    if "monk" in cis:
        ac = max(ac, 10 + dex + _mod(scores["wis"]))
    return ac


def saving_throws(cat, scores, prof_bonus, primary_ci) -> dict:
    """Per ability: modifier (+ prof bonus where the primary class is proficient) and the flag.
    Multiclass grants saving-throw proficiencies from the first class only (RAW)."""
    prof = {st["index"] for st in cat.record("classes", primary_ci).get("saving_throws", [])}
    return {ab: {"modifier": _mod(scores[ab]) + (prof_bonus if ab in prof else 0),
                 "proficient": ab in prof}
            for ab in cat.get("abilities")}


# ── skills ────────────────────────────────────────────────────────────────────
def skill_table(cat, scores, prof_bonus, choices) -> dict:
    """Every skill: ability modifier (+ prof if chosen, + prof again for expertise) and the flags."""
    chosen = {H._norm(s) for s in choices.get("skill_choices", [])}
    expert = {H._norm(s) for s in (choices.get("expertise") or [])}
    out = {}
    for s in cat.records("skills").values():
        ab = s["ability_score"]["index"]
        nm = H._norm(s["name"])
        proficient, expertise = nm in chosen, nm in expert
        total = _mod(scores[ab]) + (prof_bonus if proficient else 0) + (prof_bonus if expertise else 0)
        out[s["name"]] = {"modifier": total, "ability": ab,
                          "proficient": proficient, "expertise": expertise}
    return out


# ── spellcasting ──────────────────────────────────────────────────────────────
def spell_stats(cat, scores, prof_bonus, classes) -> dict:
    """{class name: {ability, save_dc, attack_bonus}} for each class that can cast at its level."""
    out = {}
    for ci, lv in classes:
        c = cat.record("classes", ci)
        sc = (c or {}).get("spellcasting")
        if not sc or not (H.has_slots(cat, ci, lv) or H.cantrips_known(cat, ci, lv)):
            continue
        ab = sc["spellcasting_ability"]["index"]
        mod = _mod(scores[ab])
        out[c["name"]] = {"ability": ab, "save_dc": 8 + prof_bonus + mod, "attack_bonus": prof_bonus + mod}
    return out


# ── speed (race / subrace) ────────────────────────────────────────────────────
def _race_speed(cat, race) -> int:
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    sub = cat.record("subraces", idx)
    if sub:
        parent = cat.record("races", sub.get("race", {}).get("index"))
        return (parent or {}).get("speed", 30)
    return (cat.record("races", idx) or {}).get("speed", 30)


# ── assembly ──────────────────────────────────────────────────────────────────
def derive(cat, choices) -> dict:
    """Compute the full sheet from the choices. Returns the derived numbers (the choices themselves
    stay in the response alongside this)."""
    classes = _classes(choices)
    scores = ability_scores(cat, choices)
    mods = {ab: _mod(s) for ab, s in scores.items()}
    total_level = sum(lv for _, lv in classes)
    pb = proficiency_bonus(total_level)
    skills = skill_table(cat, scores, pb, choices)
    perception = next((v["modifier"] for k, v in skills.items() if H._norm(k) == "perception"), 0)
    return {
        "level": total_level,
        "proficiency_bonus": pb,
        "ability_scores": scores,
        "ability_modifiers": mods,
        "max_hp": max_hp(cat, classes, mods["con"]),
        "hit_dice": hit_dice(cat, classes),
        "armor_class": armor_class(cat, scores, classes),
        "initiative": mods["dex"],
        "speed": _race_speed(cat, choices["race"]),
        "saving_throws": saving_throws(cat, scores, pb, classes[0][0]),
        "skills": skills,
        "passive_perception": 10 + perception,
        "spellcasting": spell_stats(cat, scores, pb, classes),
    }
