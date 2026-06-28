"""Character sheet generator — translate a request into the right resources, build the per-request
grammar + prompt, send it to the model, and repair the result into valid-by-construction choices.

The model picks; the compute lives in pure helpers (helpers.py). This module assembles the sheet.
Base contract: name / background / alignment / skills / spells; race / abilities / classes (+ the
code-resolved subclass) are injected by code. Feature choices (features.py) and starting equipment
(equipment.py) are merged on top of the base contract."""
import random

from app.generation import client, equipment, features
from app.generation import helpers as H


def build_grammar(cat, race, classes, subclasses):
    """(model_schema, fixed_fields). classes: [(ci, lv)]; subclasses aligned (None where unlocked-not)."""
    primary = classes[0][0]
    aa = H.ability_assignment(cat, primary)
    n_skill, skill_idx = H.class_skill_grant(cat, primary)

    props = {
        "name": {"type": "string"},
        "background": {"enum": cat.get("backgrounds")},
        "alignment": {"enum": cat.get("alignments_display")},
        "skill_choices": {"type": "array", "items": {"enum": H.skill_names(cat, skill_idx)},
                          "minItems": n_skill, "maxItems": n_skill, "uniqueItems": True},
    }
    req = ["name", "background", "alignment", "skill_choices"]

    resolved = [(ci, lv, sub) for (ci, lv), sub in zip(classes, subclasses)]
    pools = H.spell_pools(cat, resolved, race, aa)
    if pools:
        cant, spl, nc, ns = pools
        props["spell_choices"] = {
            "type": "object",
            "properties": {
                "cantrips": {"type": "array", "items": {"enum": cant},
                             "minItems": nc, "maxItems": nc, "uniqueItems": True},
                "spells": {"type": "array", "items": {"enum": spl},
                           "minItems": ns, "maxItems": ns, "uniqueItems": True},
            },
            "required": ["cantrips", "spells"],
        }
        req.append("spell_choices")

    fp, freq = features.feature_props(cat, resolved, race)   # fighting style, expertise, feats, …
    props.update(fp)
    req += freq

    ep, ereq = equipment.equipment_props(cat, classes)       # starting-equipment routes (primary class)
    props.update(ep)
    req += ereq

    fixed = {
        "race": race,
        "ability_assignment": aa,
        "classes": [{"class": ci.capitalize(), "level": lv, **({"subclass": sub} if sub else {})}
                    for (ci, lv), sub in zip(classes, subclasses)],
    }
    return {"type": "object", "properties": props, "required": req}, fixed


def build_prompt(cat, race, classes, subclasses, unique=None):
    """ChatML: the locked sheet system prompt + the subclass-resolved request (+ optional hint)."""
    desc = " / ".join(f"{ci} {lv}" + (f" ({sub})" if sub else "")
                      for (ci, lv), sub in zip(classes, subclasses))
    user = f"Make a {race}: {desc}."
    if unique:
        user += f' What is unique about this character: "{unique}".'
    return (f"<|im_start|>system\n{cat.get('prompt_sheet_sys')}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def generate(cat, spec, *, rng=random):
    """Orchestrator: request → resolve subclasses → grammar + prompt → model → repair → choices."""
    subclasses = H.resolve_subclasses(cat, spec.classes, spec.subclasses, rng)
    schema, fixed = build_grammar(cat, spec.race, spec.classes, subclasses)
    text = build_prompt(cat, spec.race, spec.classes, subclasses, spec.unique)
    raw = client.generate(text, schema)
    choices = {**raw, **fixed}
    H.repair(cat, choices, spec.race, spec.classes, subclasses)
    resolved = [(ci, lv, sub) for (ci, lv), sub in zip(spec.classes, subclasses)]
    features.repair_features(cat, choices, resolved, spec.race)
    return equipment.repair_equipment(cat, choices, spec.classes)
