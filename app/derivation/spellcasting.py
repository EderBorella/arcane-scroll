"""Spellcasting stats — save DC + attack bonus per casting class. (Spell slots by level and
level-bucketing of the chosen spells join this module next.)"""
from app.derivation.abilities import modifier
from app.generation import helpers as H


def spell_stats(cat, scores, prof_bonus, classes) -> dict:
    """{class name: {ability, save_dc, attack_bonus}} for each class that can cast at its level."""
    out = {}
    for ci, lv in classes:
        c = cat.record("classes", ci)
        sc = (c or {}).get("spellcasting")
        if not sc or not (H.has_slots(cat, ci, lv) or H.cantrips_known(cat, ci, lv)):
            continue
        ab = sc["spellcasting_ability"]["index"]
        mod = modifier(scores[ab])
        out[c["name"]] = {"ability": ab, "save_dc": 8 + prof_bonus + mod, "attack_bonus": prof_bonus + mod}
    return out
