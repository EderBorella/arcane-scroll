"""Derivation engine — assemble a full character sheet from the model's (repaired) choices.

`derive(cat, choices, *, rng)` is a thin orchestrator over the per-concern compute modules
(abilities, vitals, proficiency, spellcasting, features) — each a group of named pure helpers,
unit-testable in isolation. The model picked; this computes.

`rng` exists only for language choices (race/background "choose N of your choice"); pass a seeded RNG
for a reproducible sheet. Everything else is a pure function of the choices.

Deferred (data/scope, not oversight):
  * Armour AC from equipped items — no item-stat records yet → unarmoured base (see vitals).
  * Feat mechanical effects — only ASI bumps are applied (see abilities).
  * Equipment assembly + treasure/starting wealth — no item-stat/wealth records.
"""
import random

from app.derivation import abilities, features, proficiency, spellcasting, vitals

SCHEMA_VERSION = 1


def derive(cat, choices, *, rng=random) -> dict:
    classes = abilities.class_levels(choices)
    scores = abilities.ability_scores(cat, choices, classes)
    mods = {ab: abilities.modifier(s) for ab, s in scores.items()}
    total_level = sum(lv for _, lv in classes)
    pb = proficiency.proficiency_bonus(total_level)
    skills = proficiency.skill_table(cat, scores, pb, choices)
    return {
        "schema_version": SCHEMA_VERSION,
        "level": total_level,
        "xp": 0,
        "proficiency_bonus": pb,
        "ability_scores": scores,
        "ability_modifiers": mods,
        "max_hp": vitals.max_hp(cat, classes, mods["con"]),
        "hit_dice": vitals.hit_dice(cat, classes),
        "death_saves": {"successes": 0, "failures": 0},
        "armor_class": vitals.armor_class(cat, scores, classes),
        "initiative": mods["dex"],
        "speed": vitals.speed(cat, choices["race"]),
        "saving_throws": proficiency.saving_throws(cat, scores, pb, classes[0][0]),
        "skills": skills,
        "passive_perception": proficiency.passive_perception(skills),
        "proficiencies": proficiency.proficiencies(cat, classes, choices.get("background")),
        "languages": proficiency.languages(cat, choices["race"], choices.get("background"), rng),
        "features": features.features_and_traits(cat, choices),
        "spellcasting": spellcasting.spell_stats(cat, scores, pb, classes),
        "spell_slots": spellcasting.spell_slots(cat, classes),
        "spells": spellcasting.spellbook(cat, choices),
    }
