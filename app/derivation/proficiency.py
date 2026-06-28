"""Proficiency-derived stats — proficiency bonus, saving throws, the skill table (with expertise +
sources), passive perception, armour/weapon/tool proficiencies, and languages."""
import random
import re

from app.derivation.abilities import modifier
from app.generation import helpers as H

_ARMOR = {"all-armor", "light-armor", "medium-armor", "heavy-armor", "shields"}


def proficiency_bonus(total_level: int) -> int:
    return 2 + (total_level - 1) // 4


def saving_throws(cat, scores, prof_bonus, primary_ci) -> dict:
    """Per ability: modifier (+ prof bonus where the primary class is proficient) and the flag.
    Multiclass grants saving-throw proficiencies from the first class only (RAW)."""
    prof = {st["index"] for st in cat.record("classes", primary_ci).get("saving_throws", [])}
    return {ab: {"modifier": modifier(scores[ab]) + (prof_bonus if ab in prof else 0),
                 "proficient": ab in prof}
            for ab in cat.get("abilities")}


def _background(cat, name):
    """The background record matching a chosen background name (or None)."""
    if not name:
        return None
    n = H._norm(name)
    return next((b for b in cat.records("backgrounds").values() if H._norm(b.get("name")) == n), None)


def skill_table(cat, scores, prof_bonus, choices) -> dict:
    """Every skill: ability modifier (+ prof if proficient, + prof again for expertise), plus the
    `source` of the proficiency (class pick or background grant)."""
    chosen = {H._norm(s) for s in choices.get("skill_choices", [])}
    expert = {H._norm(s) for s in (choices.get("expertise") or [])}
    bg = _background(cat, choices.get("background"))
    bg_skills = {H._norm(p["name"]) for p in (bg or {}).get("starting_proficiencies", [])
                 if p.get("index", "").startswith("skill-")}
    out = {}
    for s in cat.records("skills").values():
        ab, nm = s["ability_score"]["index"], H._norm(s["name"])
        from_class, from_bg, expertise = nm in chosen, nm in bg_skills, nm in expert
        proficient = from_class or from_bg
        total = modifier(scores[ab]) + (prof_bonus if proficient else 0) + (prof_bonus if expertise else 0)
        out[s["name"]] = {"modifier": total, "ability": ab, "proficient": proficient,
                          "expertise": expertise,
                          "source": "class" if from_class else ("background" if from_bg else None)}
    return out


def passive_perception(skills) -> int:
    return 10 + next((v["modifier"] for k, v in skills.items() if H._norm(k) == "perception"), 0)


def proficiencies(cat, classes, background=None) -> dict:
    """Armour & weapon proficiencies from the primary class (RAW: these come from the first class on
    a multiclass), plus the background's tool proficiencies."""
    armor, weapons = [], []
    for p in cat.record("classes", classes[0][0]).get("proficiencies", []):
        idx, name = p.get("index", ""), p.get("name", "")
        if idx in _ARMOR:
            armor.append(name)
        elif "weapon" in idx:
            weapons.append(name)
    tools = list((_background(cat, background) or {}).get("tool_proficiencies", []))
    return {"armor": armor, "weapons": weapons, "tools": tools}


def _race_languages(cat, race):
    """(fixed language names, language_options dict) for a race — merging a subrace with its parent."""
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    recs = []
    sub = cat.record("subraces", idx)
    if sub:
        recs.append(sub)
        parent = cat.record("races", sub.get("race", {}).get("index"))
        if parent:
            recs.append(parent)
    elif cat.record("races", idx):
        recs.append(cat.record("races", idx))
    fixed = [l["name"] for r in recs for l in r.get("languages", [])]
    opt = next((r["language_options"] for r in recs if r.get("language_options")), None)
    return fixed, opt


def languages(cat, race, background=None, rng=random) -> list:
    """Common + the race's own languages, then a random pick from the race's options, then the
    background's "choose N of your choice" drawn from the full language list."""
    fixed, opt = _race_languages(cat, race)
    out = list(dict.fromkeys(["Common"] + fixed))

    if opt and opt.get("from", {}).get("option_set_type") == "options_array":
        pool = [o["item"]["name"] for o in opt["from"]["options"] if o["item"]["name"] not in out]
        n = min(opt.get("choose", 0), len(pool))
        if n:
            out += rng.sample(pool, n)

    bg = _background(cat, background)
    if bg:
        universe = [l["name"] for l in cat.records("languages").values()]
        pool = [l for l in universe if l not in out]
        n = min(bg.get("language_options", {}).get("choose", 0), len(pool))
        if n:
            out += rng.sample(pool, n)
    return out
