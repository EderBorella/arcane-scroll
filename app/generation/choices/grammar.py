"""Build the model-facing grammar — the JSON schema that constrains what the model may pick for a
build. Two passes mirror the model-call seam kept from the original generator: pass 1 is the whole
sheet except starting equipment; pass 2 is the starting-equipment bundle. Every enumerated option is
read from the DAL (see options.py), so the grammar is content-neutral and follows the loaded ruleset.

The grammar's job is to bound the choice space — *what may be chosen* — not to decide the code-fixed
fields (species, classes, base ability scores), which the assembler injects. The loaded ruleset shows in
the shape: there is a background ability-boost choice (a species carries no ability bonus) and no
racial-bonus field anywhere.
"""
from app.generation.choices import options


def build_pass1_grammar(access, spec, resolved, *, feat_slots=0):
    """The pass-1 model schema. The model picks a name, the background ability-boost distribution
    (constrained to the background's allowed abilities), the first class's skill proficiencies, the
    caster spell selection (when the build casts), and any ability-increase-slot feats (only when
    ``feat_slots`` > 0). Fields with an empty option space are omitted rather than offered empty."""
    props = {"name": {"type": "string"}}
    req = ["name"]

    if spec.background:
        boost = _boost_schema(options.background_boost_options(access, spec.background))
        if boost is not None:
            props["background_increase"] = boost
            req.append("background_increase")

    first_class = resolved[0][0]
    n_skill, pool = options.skill_choice(access, first_class)
    if n_skill:
        props["skills"] = {"type": "array", "items": {"enum": pool},
                           "minItems": n_skill, "maxItems": n_skill, "uniqueItems": True}
        req.append("skills")

    cantrips, leveled = options.spell_pools(access, resolved)
    if cantrips is not None:
        props["spells"] = {
            "type": "object",
            "properties": {
                "cantrips": {"type": "array", "items": {"enum": cantrips}, "uniqueItems": True},
                "spells": {"type": "array", "items": {"enum": leveled}, "uniqueItems": True},
            },
            "required": ["cantrips", "spells"],
        }
        req.append("spells")

    if feat_slots > 0:
        base = options.base_ability_scores(access, first_class)
        boost = options.default_background_boost(access, spec.background) if spec.background else {}
        total_level = sum(lv for _cid, lv, _sub in resolved)
        feat_pool = options.eligible_feats(access, base, boost, total_level)
        if feat_pool:
            props["feats"] = {"type": "array", "items": {"enum": feat_pool},
                              "minItems": feat_slots, "maxItems": feat_slots, "uniqueItems": True}
            req.append("feats")

    return {"type": "object", "properties": props, "required": req}


def _boost_schema(opts):
    """The background-boost choice as a ``oneOf`` over the two legal shapes — +2/+1 to two of the
    background's ability options, or +1/+1/+1 to three. None when the background offers too few
    options for even the {2,1} shape (the assembler then falls back to no boost)."""
    if len(opts) < 2:
        return None
    branches = [{
        "type": "object", "additionalProperties": False,
        "properties": {"shape": {"const": "two-one"},
                       "plus_two": {"enum": opts}, "plus_one": {"enum": opts}},
        "required": ["shape", "plus_two", "plus_one"],
    }]
    if len(opts) >= 3:
        branches.append({
            "type": "object", "additionalProperties": False,
            "properties": {"shape": {"const": "one-one-one"},
                           "abilities": {"type": "array", "items": {"enum": opts},
                                         "minItems": 3, "maxItems": 3, "uniqueItems": True}},
            "required": ["shape", "abilities"],
        })
    return {"oneOf": branches}


def build_equipment_grammar(access, spec, resolved):
    """The pass-2 model schema — the starting-equipment bundle the model picks for each owner (the
    primary class and, when present, the background). Each owner with bundles becomes an enum field of
    its bundle ids. The schema has no properties when neither owner offers bundles (pass 2 is then
    skipped by the orchestrator)."""
    props: dict = {}
    req: list = []
    owners = [("class", resolved[0][0])]
    if spec.background:
        owners.append(("background", spec.background))
    for owner_kind, owner_id in owners:
        bundles = options.equipment_bundles(access, owner_kind, owner_id)
        if bundles:
            field = f"equipment_{owner_kind}"
            props[field] = {"enum": [bid for bid, _label in bundles]}
            req.append(field)
    return {"type": "object", "properties": props, "required": req}
