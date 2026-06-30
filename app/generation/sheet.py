"""Character sheet generator — translate a request into the right resources, build the per-request
grammar + prompt, send it to the model, and repair the result into valid-by-construction choices.

The model picks; the compute lives in pure helpers (helpers.py). This module assembles the sheet.
Base contract: name / background / alignment / skills / spells; race / abilities / classes (+ the
code-resolved subclass) are injected by code. Feature choices (features.py) and starting equipment
(equipment.py) are merged on top of the base contract."""
import random

from app.generation import client, equipment, features
from app.generation import helpers as H


def predecide(cat, spec, resolved, rng):
    """Fields decided in code *before* the model call (variety spread), so the model can't monopolise
    them and any explicit value is honoured. Background is always picked; a fighting style is picked
    when exactly one class grants one (the multi-grant case is left to the model). Precedence:
    explicit (spec / future decoder) → seeded random."""
    out = {}
    backgrounds = cat.get("backgrounds") or []
    bg = spec.background or (rng.choice(backgrounds) if backgrounds else None)
    if bg:
        out["background"] = bg
    granting = features._fighting_style_classes(cat, resolved)
    if spec.fighting_style:
        out["fighting_style"] = spec.fighting_style
    elif len(granting) == 1:
        styles = sorted(set(cat.get("fighting_styles", {}).get(granting[0], [])))
        if styles:
            out["fighting_style"] = rng.choice(styles)
    return out


def build_grammar(cat, race, classes, subclasses, *, predecided=None):
    """(model_schema, fixed_fields) for PASS 1 — the whole sheet *except* starting equipment (a separate
    second pass) and any `predecided` fields (background / fighting style), which are injected as fixed
    so the model neither picks nor overrides them. classes: [(ci, lv)]; subclasses aligned."""
    predecided = predecided or {}
    primary = classes[0][0]
    resolved = [(ci, lv, sub) for (ci, lv), sub in zip(classes, subclasses)]
    aa = H.ability_assignment(cat, resolved)                  # combined multiclass + subclass priority
    n_skill, skill_idx = H.class_skill_grant(cat, primary)

    props = {
        "name": {"type": "string"},
        "alignment": {"enum": cat.get("alignments_display")},
        "skill_choices": {"type": "array", "items": {"enum": H.skill_names(cat, skill_idx)},
                          "minItems": n_skill, "maxItems": n_skill, "uniqueItems": True},
    }
    req = ["name", "alignment", "skill_choices"]
    if "background" not in predecided:                        # fallback: let the model pick if not pre-set
        props["background"] = {"enum": cat.get("backgrounds")}
        req.append("background")

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
    if "fighting_style" in predecided:                       # pre-decided → not a model choice
        fp.pop("fighting_style", None)
        freq = [f for f in freq if f != "fighting_style"]
    props.update(fp)
    req += freq

    fixed = {
        "race": race,
        "ability_assignment": aa,
        "classes": [{"class": ci.capitalize(), "level": lv, **({"subclass": sub} if sub else {})}
                    for (ci, lv), sub in zip(classes, subclasses)],
        **predecided,
    }
    return {"type": "object", "properties": props, "required": req}, fixed


def build_equipment_grammar(cat, classes, fighting_style=None):
    """(model_schema, required) for PASS 2 — only the primary class's starting-equipment slots,
    constrained to the character's fighting style (so the routes/weapons offered already fit it)."""
    props, req = equipment.equipment_props(cat, classes, fighting_style)
    return {"type": "object", "properties": props, "required": req}, req


def build_equipment_prompt(cat, race, classes_field, fighting_style, ability_assignment):
    """ChatML for pass 2: the equipment system prompt + a short build summary (class, style, strongest
    abilities) so the model picks weapons/gear coherent with the character built in pass 1."""
    desc = " / ".join(f"{c.get('class')} {c.get('level')}" + (f" ({c['subclass']})" if c.get("subclass") else "")
                      for c in classes_field)
    aa = ability_assignment or {}
    top = ", ".join(sorted(aa, key=lambda a: -aa.get(a, 0))[:2])
    bits = [f"{race} {desc}"]
    if fighting_style:
        bits.append(f"fighting style: {fighting_style}")
    if top:
        bits.append(f"strongest abilities: {top}")
    user = ("Choose this character's starting equipment — pick options that fit the build (a weapon "
            "matching the fighting style and ability scores).\n" + "; ".join(bits) + ".")
    return (f"<|im_start|>system\n{cat.prompt('equip_sys')}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def build_prompt(cat, race, classes, subclasses, unique=None):
    """ChatML: the locked sheet system prompt + the subclass-resolved request (+ optional hint)."""
    desc = " / ".join(f"{ci} {lv}" + (f" ({sub})" if sub else "")
                      for (ci, lv), sub in zip(classes, subclasses))
    user = f"Make a {race}: {desc}."
    if unique:
        user += f' What is unique about this character: "{unique}".'
    return (f"<|im_start|>system\n{cat.prompt('sheet_sys')}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def generate(cat, spec, *, rng=random):
    """Two-pass orchestrator. Pass 1: the sheet minus equipment. Pass 2 (skipped when the character
    takes gold instead of equipment): pick starting equipment, prompted with the pass-1 build so the
    gear fits the fighting style / abilities. Each pass is grammar-constrained and repaired."""
    subclasses = H.resolve_subclasses(cat, spec.classes, spec.subclasses, rng)
    resolved = [(ci, lv, sub) for (ci, lv), sub in zip(spec.classes, subclasses)]

    # pass 1 — everything but equipment; background/fighting-style are pre-decided in code (variety)
    predecided = predecide(cat, spec, resolved, rng)
    schema, fixed = build_grammar(cat, spec.race, spec.classes, subclasses, predecided=predecided)
    raw = client.generate(build_prompt(cat, spec.race, spec.classes, subclasses, spec.unique), schema)
    choices = {**raw, **fixed, "roll_starting_wealth": spec.roll_wealth}
    H.repair(cat, choices, spec.race, spec.classes, subclasses, fixed["ability_assignment"])
    features.repair_features(cat, choices, resolved, spec.race)

    # pass 2 — starting equipment, fitted to the built character (unless taking gold instead)
    if not spec.roll_wealth:
        style = choices.get("fighting_style")
        eq_schema, eq_req = build_equipment_grammar(cat, spec.classes, style)
        if eq_req:                                 # primary class has equipment slots
            eq_prompt = build_equipment_prompt(cat, spec.race, choices["classes"], style,
                                               choices.get("ability_assignment"))
            choices.update(client.generate(eq_prompt, eq_schema))
        equipment.repair_equipment(cat, choices, spec.classes)
    return choices
