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


def build_pass1_grammar(access, spec, resolved, *, feat_slots=0, boon_slots=0):
    """The pass-1 model schema. The model picks a name, the background ability-boost distribution
    (constrained to the background's allowed abilities), the first class's skill proficiencies, the
    caster spell selection (when the build casts), the weapon-mastery picks (when the build gains a
    weapon-mastery feature), any ability-increase-slot feats plus their chosen increase targets (only
    when ``feat_slots`` > 0), and any top-tier boon-slot picks (only when ``boon_slots`` > 0). Fields
    with an empty option space are omitted rather than offered empty."""
    props = {"name": {"type": "string"}}
    req = ["name"]

    # Species sub-choices: a lineage pick and/or a variant-axis pick, offered only when the chosen
    # species carries them (and never when it doesn't). Lineage is enumerated as ids (a resolver dim
    # the deriver renders to its display name); the variant axis is enumerated as option names (a
    # name-keyed field the deriver carries verbatim). Each is required once offered, so a species that
    # has them always yields its pick.
    lineage_ids = options.lineage_options(access, spec.species)
    if lineage_ids:
        props["lineage"] = {"enum": lineage_ids}
        req.append("lineage")
    variant_names = options.variant_option_names(access, spec.species)
    if variant_names:
        props["species_variant"] = {"enum": variant_names}
        req.append("species_variant")

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

    n_wm, wm_pool = options.weapon_mastery_choice(access, resolved)
    if n_wm > 0:
        # A build with a weapon-mastery feature picks ``n_wm`` distinct masterable weapons.
        props["weapon_masteries"] = {"type": "array", "items": {"enum": wm_pool},
                                     "minItems": n_wm, "maxItems": n_wm, "uniqueItems": True}
        req.append("weapon_masteries")

    # Tool / language / expertise proficiency choices. These are offered as free string arrays sized
    # to the build's required count — deliberately WITHOUT an option enum: the candidate pools are the
    # reference source's curated menus, so emitting them would leak copyrighted content. The model /
    # user supplies ids; the assembler validates each pick against the grant (a single-id membership
    # test) and the completeness pass flags an under-filled choice against the known count.
    n_lang, _grants = options.language_choice(access, resolved, spec)
    if n_lang:
        props["languages"] = {"type": "array", "items": {"type": "string"},
                              "minItems": n_lang, "maxItems": n_lang, "uniqueItems": True}
        req.append("languages")

    n_tool, _grants = options.tool_choice(access, resolved, spec)
    if n_tool:
        props["tools"] = {"type": "array", "items": {"type": "string"},
                          "minItems": n_tool, "maxItems": n_tool, "uniqueItems": True}
        req.append("tools")

    n_exp, _grants = options.expertise_choice(access, resolved, spec)
    if n_exp:
        props["expertise"] = {"type": "array", "items": {"type": "string"},
                              "minItems": n_exp, "maxItems": n_exp, "uniqueItems": True}
        req.append("expertise")

    total_level = sum(lv for _cid, lv, _sub in resolved)
    boost = options.default_background_boost(access, spec.background) if spec.background else {}
    base = options.base_ability_scores(access, first_class)

    if feat_slots > 0:
        # Each ability-increase/feat slot is spent on a general feat OR a raw ability-score increase.
        # The raw increase is itself one of the general feats, so a single general-feat pool models
        # the whole "ability increase OR feat" choice — no separate branch is needed.
        # Feat eligibility is gated against the DEFAULT background boost, not the model's not-yet-made
        # pick: the grammar is built before the model chooses its boost distribution, so ability-prereq
        # gating uses the deterministic default (+2/+1 to the background's first two options). A model
        # pick that shifts the boost elsewhere is a rare, minor mismatch; the assembler's feat-increase
        # allocation then reads the actual picked boost, and the validator has the final say on legality.
        feat_pool = options.eligible_feats(access, base, boost, total_level)
        if feat_pool:
            feats_schema = {"type": "array", "items": {"enum": feat_pool},
                            "minItems": feat_slots, "maxItems": feat_slots}
            # A repeatable feat (the raw ability-score-increase) may fill several slots, so uniqueness
            # can't be a blanket schema rule. Only apply ``uniqueItems`` when NO eligible feat repeats
            # (duplicates would then always be illegal); otherwise the assembler drops duplicate
            # non-repeatables. In the unique case, clamp the count to the pool size so a build with
            # more slots than distinct feats still yields a satisfiable schema.
            if not options.any_repeatable(access, feat_pool):
                n = min(feat_slots, len(feat_pool))
                feats_schema.update(minItems=n, maxItems=n, uniqueItems=True)
            props["feats"] = feats_schema
            req.append("feats")

            # Per-slot ability-increase target: when a slot is spent on a raw (from-any) increase, the
            # model chooses which ability(ies) it raises — a single-target +2 ("two") or a +1/+1
            # split ("split") across two distinct abilities. Targets are constrained to actual ability
            # ids, so the pick is legal by construction. Optional: a slot may take a feat instead, and
            # any slot without a supplied target falls back to the deterministic allocation.
            if options.any_choosable_increase(access, feat_pool):
                ability_ids = [r["id"] for r in options.catalog.list_abilities(access)]
                props["ability_increases"] = {
                    "type": "array", "maxItems": feat_slots,
                    "items": {"oneOf": [
                        {"type": "object", "additionalProperties": False,
                         "required": ["shape", "ability"],
                         "properties": {"shape": {"const": "two"},
                                        "ability": {"enum": ability_ids}}},
                        {"type": "object", "additionalProperties": False,
                         "required": ["shape", "abilities"],
                         "properties": {"shape": {"const": "split"},
                                        "abilities": {"type": "array", "items": {"enum": ability_ids},
                                                      "minItems": 2, "maxItems": 2,
                                                      "uniqueItems": True}}},
                    ]},
                }

    if boon_slots > 0:
        # The top-tier boon slot draws from its OWN feat category (distinct from the general pool),
        # so a max-level build no longer under-offers by one slot. Same repeatability/clamp handling
        # as the general slots.
        boon_pool = options.eligible_feats(access, base, boost, total_level, category="epic-boon")
        if boon_pool:
            boon_schema = {"type": "array", "items": {"enum": boon_pool},
                           "minItems": boon_slots, "maxItems": boon_slots}
            if not options.any_repeatable(access, boon_pool):
                n = min(boon_slots, len(boon_pool))
                boon_schema.update(minItems=n, maxItems=n, uniqueItems=True)
            props["boons"] = boon_schema
            req.append("boons")

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
