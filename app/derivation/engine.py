"""Derivation engine — assemble a full character sheet from the model's (repaired) choices.

Pure: no model, no side-effects. `derive(cat, choices)` is a thin orchestrator over the per-concern
compute modules (abilities, vitals, proficiency, spellcasting, …) — each a group of named pure
helpers, unit-testable in isolation. The model picked; this computes.

Deferred (data/scope, not oversight):
  * Armour AC from equipped items — no item-stat records yet → unarmoured base (see vitals).
  * Feat mechanical effects — only ASI bumps are applied (see abilities).
Follow-up (pure compute, per the field-inventory reference): features & traits, proficiencies &
languages, spell slots, spell bucketing, and scaffold/meta.
"""
from app.derivation import abilities, proficiency, spellcasting, vitals


def derive(cat, choices) -> dict:
    classes = abilities.class_levels(choices)
    scores = abilities.ability_scores(cat, choices, classes)
    mods = {ab: abilities.modifier(s) for ab, s in scores.items()}
    total_level = sum(lv for _, lv in classes)
    pb = proficiency.proficiency_bonus(total_level)
    skills = proficiency.skill_table(cat, scores, pb, choices)
    return {
        "level": total_level,
        "proficiency_bonus": pb,
        "ability_scores": scores,
        "ability_modifiers": mods,
        "max_hp": vitals.max_hp(cat, classes, mods["con"]),
        "hit_dice": vitals.hit_dice(cat, classes),
        "armor_class": vitals.armor_class(cat, scores, classes),
        "initiative": mods["dex"],
        "speed": vitals.speed(cat, choices["race"]),
        "saving_throws": proficiency.saving_throws(cat, scores, pb, classes[0][0]),
        "skills": skills,
        "passive_perception": proficiency.passive_perception(skills),
        "spellcasting": spellcasting.spell_stats(cat, scores, pb, classes),
    }
