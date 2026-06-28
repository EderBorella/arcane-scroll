"""Proficiency-derived stats — proficiency bonus, saving throws, the skill table (with expertise),
and passive perception. (Armour/weapon/tool proficiencies + languages join this module next.)"""
from app.derivation.abilities import modifier
from app.generation import helpers as H


def proficiency_bonus(total_level: int) -> int:
    return 2 + (total_level - 1) // 4


def saving_throws(cat, scores, prof_bonus, primary_ci) -> dict:
    """Per ability: modifier (+ prof bonus where the primary class is proficient) and the flag.
    Multiclass grants saving-throw proficiencies from the first class only (RAW)."""
    prof = {st["index"] for st in cat.record("classes", primary_ci).get("saving_throws", [])}
    return {ab: {"modifier": modifier(scores[ab]) + (prof_bonus if ab in prof else 0),
                 "proficient": ab in prof}
            for ab in cat.get("abilities")}


def skill_table(cat, scores, prof_bonus, choices) -> dict:
    """Every skill: ability modifier (+ prof if chosen, + prof again for expertise) and the flags."""
    chosen = {H._norm(s) for s in choices.get("skill_choices", [])}
    expert = {H._norm(s) for s in (choices.get("expertise") or [])}
    out = {}
    for s in cat.records("skills").values():
        ab = s["ability_score"]["index"]
        nm = H._norm(s["name"])
        proficient, expertise = nm in chosen, nm in expert
        total = modifier(scores[ab]) + (prof_bonus if proficient else 0) + (prof_bonus if expertise else 0)
        out[s["name"]] = {"modifier": total, "ability": ab,
                          "proficient": proficient, "expertise": expertise}
    return out


def passive_perception(skills) -> int:
    return 10 + next((v["modifier"] for k, v in skills.items() if H._norm(k) == "perception"), 0)
