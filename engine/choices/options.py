"""Pure, DAL-grounded enumeration + allocation for the choice grammar.

Two responsibilities, both content-neutral (every value read from the loaded ruleset via the
generator data-access layer, never a game literal):

* **Enumerate** the option space the grammar constrains the model to — a class's subclasses, its
  skill pool, a caster's spell pool, the eligible feat pool, and the starting-equipment bundles.
* **Allocate** the code-decided fields — the base ability array (a class's suggested standard-array
  assignment) and the default background ability boost. (The background's origin feat is added by the
  CORE deriver directly from the background, so it is not one of the model's choices and has no
  enumerator here.)

The loaded ruleset's model is baked into what is (and isn't) here: a *species* carries no ability bonus, so
there is no species-bonus reader; the ability boost and the origin feat come from the *background*.
No model I/O and no writes — the two-pass model seam lives in the orchestrator.
"""
import random

from access.generator import backgrounds as bg_q
from access.generator import catalog
from access.generator import classes as class_q
from access.generator import equipment as equip_q
from access.generator import feats as feat_q
from access.generator import proficiencies as prof_q
from access.generator import spells as spell_q
from access.generator import species as species_q

# The ability score at which the modifier is zero — the neutral baseline the standard-array
# allocation falls back to for any ability a class's suggested assignment does not cover. In a
# complete ruleset the suggested assignment covers every ability, so this fallback is inert; it only
# fills a ruleset that carries more abilities than the suggested array assigns. (The same
# modifier-origin is baked into the shared ``(score - 10) // 2`` modifier arithmetic.)
_MODIFIER_ZERO_SCORE = 10


# --------------------------------------------------------------------------- subclass
def resolve_subclass(access, class_id, level, override=None, rng=random):
    """The subclass for one class entry: the override when the class has unlocked its subclass and
    the override is one of the class's options, else a deterministic-by-``rng`` pick once the unlock
    level is reached, else None (the level has not unlocked a subclass)."""
    unlock = class_q.subclass_unlock_level(access, class_id)
    if unlock is None or level < unlock:
        return None
    options = [r["id"] for r in class_q.subclasses_for_class(access, class_id)]
    if not options:
        return None
    if override in options:
        return override
    return rng.choice(options)


# --------------------------------------------------------------------------- species sub-choices
def lineage_options(access, species_id):
    """The lineage ids a species offers as a sub-choice, ordered. Empty when the species has none —
    the grammar then offers no lineage field. A build picks exactly one when the list is non-empty."""
    return [r["id"] for r in species_q.species_lineages(access, species_id)]


def variant_option_names(access, species_id):
    """The variant option NAMES a species offers as a sub-choice, in (axis, id) order with duplicates
    removed. A species's variant axis is a name-keyed pick (matched by (species, axis, option_name)),
    so the sheet's single ``species_variant`` string carries the chosen option name directly. Empty
    when the species has no variant axis. (The reference model gives a species at most one variant
    axis; were several ever added, the single-string sheet field would need a contract change.)"""
    seen: set = set()
    out: list = []
    for r in species_q.species_variant_options(access, species_id):
        name = r["option_name"]
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# --------------------------------------------------------------------------- multiclass legality
# The multiclassing rule requires a score of at least this in the primary ability of the new class and
# every current class before an additional class may be taken. A rules constant (like the modifier-zero
# baseline above), not a per-class DB fact — the abilities it applies to ARE read from the reference
# data (a class's primary abilities and how they combine).
_MULTICLASS_MIN_SCORE = 13


def multiclass_prereq_shortfall(access, class_ids, scores):
    """The class ids in a build whose multiclass ability prerequisite the given effective ``scores`` do
    not meet — empty for a single-class build (the prerequisite gates a build only once it ADDS a
    class) or when every class qualifies.

    The rule: a score of at least the multiclass minimum in the primary ability of the new class AND
    every current class. A class whose primary abilities combine with an OR relation qualifies on any
    one of them; otherwise every primary ability must meet the minimum. A class with no primary ability
    on record is skipped rather than wrongly rejected. ``class_ids`` is the build's classes in request
    order; ``scores`` is ability-id keyed (base + background boost)."""
    if len(class_ids) < 2:
        return []
    out = []
    for cid in class_ids:
        abilities = [r["ability_id"] for r in class_q.class_primary_abilities(access, cid)]
        if not abilities:
            continue
        met = [scores.get(aid, 0) >= _MULTICLASS_MIN_SCORE for aid in abilities]
        qualifies = any(met) if class_q.class_primary_mode(access, cid) == "or" else all(met)
        if not qualifies:
            out.append(cid)
    return out


# --------------------------------------------------------------------------- abilities
def base_ability_scores(access, first_class_id):
    """Base ability scores (pre-boost), keyed by ability id — a class's suggested standard-array
    assignment, with every ability the assignment omits filled at the modifier-zero baseline so that
    every ability in the ruleset carries a base score (the sheet must list them all)."""
    scores = {r["ability_id"]: r["score"]
              for r in class_q.class_standard_array(access, first_class_id)}
    for row in catalog.list_abilities(access):
        scores.setdefault(row["id"], _MODIFIER_ZERO_SCORE)
    return scores


def background_boost_options(access, background_id):
    """The ability ids a background may boost, in its declared order."""
    return bg_q.background_ability_options(access, background_id)


def default_background_boost(access, background_id):
    """The default +2/+1 background boost, ability-id keyed — +2 to the background's first ability
    option, +1 to its second. Returns ``{}`` when the background offers fewer than two options (too
    few for even the {2,1} shape)."""
    opts = background_boost_options(access, background_id)
    if len(opts) < 2:
        return {}
    return {opts[0]: 2, opts[1]: 1}


# --------------------------------------------------------------------------- skills
def skill_choice(access, first_class_id):
    """``(n, pool_ids)`` the first class chooses its skill proficiencies from — the class's explicit
    pool, or every skill when the class chooses from any. ``n`` is capped at the pool size (0 when the
    class has no pool, e.g. a class whose proficiencies come entirely from its grant spine)."""
    choose_n, from_any, pool = class_q.class_skill_options(access, first_class_id)
    choose_n = choose_n or 0
    if from_any:
        pool = [r["id"] for r in catalog.list_skills(access)]
    return min(choose_n, len(pool)), pool


# ----------------------------------------------------------- tool / language / expertise choices
# The choice-space (grammar + assemble) needs the PRESENCE and required COUNTS of a build's
# tool / language / expertise proficiency choices — so the completeness pass can flag a missing pick
# and a pick can be validated. The counts are summed across the build's fixed owners (its classes,
# their resolved subclasses, the background, and the species) — mirroring how the skill-choice pool is
# the first class's alone. Feat-granted choices (a feat that grants a tool/language/skill-or-tool or
# expertise choice) are NOT summed here: a feat is itself a pass-1 pick, so its granted choices are
# resolved downstream (the same way feat-granted skills are not in the skill-choice pool). The
# per-owner reader (``access.generator.proficiencies``) already supports every owner kind, so that is
# an additive extension, not a schema gap.


def _grant_applies_at(grant, level):
    """True when a level-gated grant is active at ``level`` — a grant with no gained-at level is
    always active; otherwise ``level`` must have reached it. ``grant`` is a row with a
    ``gained_at_level`` column."""
    gate = grant["gained_at_level"]
    return gate is None or level >= gate


def _static_choice_owners(spec):
    """The build's non-class choice owners — the background and the species — as
    (owner_kind, owner_id) pairs. Their creation-time choices are gained at level 1 (no per-class
    level progression), so they are gated against the build's total level."""
    owners = []
    if spec.background:
        owners.append(("background", spec.background))
    if spec.species:
        owners.append(("species", spec.species))
    return owners


def _proficiency_choice_grants_for_build(access, target_kind, resolved, spec):
    """The applicable choose-mode proficiency grants of one ``target_kind`` across a build's fixed
    owners, as (owner_kind, owner_id, grant_row) tuples. A class contributes its ``multiclass_only=0``
    grants only as the FIRST class and its ``multiclass_only=1`` grants only as a SECONDARY class (the
    reduced multiclass proficiency set); subclass / background / species grants have no multiclass
    gating. Every grant is level-gated by the owning class's level (background / species by the total
    build level)."""
    total_level = sum(lv for _cid, lv, _sub in resolved)
    out = []
    for i, (cid, lv, sub) in enumerate(resolved):
        is_first = (i == 0)
        for g in prof_q.proficiency_choice_grants(access, "class", cid, target_kind):
            if not _grant_applies_at(g, lv):
                continue
            # multiclass_only=1 belongs to a secondary class; =0 belongs to the first class.
            if bool(g["multiclass_only"]) != (not is_first):
                continue
            out.append(("class", cid, g))
        if sub:
            for g in prof_q.proficiency_choice_grants(access, "subclass", sub, target_kind):
                if _grant_applies_at(g, lv):
                    out.append(("subclass", sub, g))
    for owner_kind, owner_id in _static_choice_owners(spec):
        for g in prof_q.proficiency_choice_grants(access, owner_kind, owner_id, target_kind):
            if _grant_applies_at(g, total_level):
                out.append((owner_kind, owner_id, g))
    return out


def language_choice(access, resolved, spec):
    """``(n, grants)`` for a build's language proficiency choices — ``n`` is the summed required count
    and ``grants`` the applicable grants (for pick validation). ``(0, [])`` when the build makes no
    language choice."""
    grants = _proficiency_choice_grants_for_build(access, "language", resolved, spec)
    return sum(g["choose_n"] or 0 for _ok, _oid, g in grants), grants


def tool_choice(access, resolved, spec):
    """``(n, grants)`` for a build's tool proficiency choices — ``n`` is the summed required count and
    ``grants`` the applicable grants (for pick validation). ``(0, [])`` when the build makes no tool
    choice."""
    grants = _proficiency_choice_grants_for_build(access, "tool", resolved, spec)
    return sum(g["choose_n"] or 0 for _ok, _oid, g in grants), grants


def language_pick_is_valid(access, resolved, spec, language_id):
    """True when ``language_id`` is a legal pick for one of the build's language choices — any
    language for a from-any grant, else a member of that grant's candidate pool. Validation only; no
    pool is emitted."""
    _n, grants = language_choice(access, resolved, spec)
    for _ok, _oid, g in grants:
        if g["from_any"]:
            if prof_q.is_language(access, language_id):
                return True
        elif prof_q.value_in_grant(access, g["id"], language_id):
            return True
    return False


def tool_pick_is_valid(access, resolved, spec, tool_id):
    """True when ``tool_id`` is a legal pick for one of the build's tool choices — any tool for a
    from-any grant, a tool in one of the grant's allowed categories, or a member of its explicit
    value pool. Validation only; no pool is emitted."""
    _n, grants = tool_choice(access, resolved, spec)
    for _ok, _oid, g in grants:
        if g["from_any"]:
            if prof_q.is_tool(access, tool_id):
                return True
            continue
        cats = prof_q.grant_tool_categories(access, g["id"])
        if cats and prof_q.tool_in_categories(access, tool_id, cats):
            return True
        if prof_q.value_in_grant(access, g["id"], tool_id):
            return True
    return False


def _expertise_choice_grants_for_build(access, resolved, spec):
    """The applicable choose-mode expertise grants across a build's fixed owners, as
    (owner_kind, owner_id, grant_row) tuples — classes (each level-gated at its own level), resolved
    subclasses, background, and species. Expertise grants carry no multiclass gating."""
    total_level = sum(lv for _cid, lv, _sub in resolved)
    out = []
    for cid, lv, sub in resolved:
        for g in prof_q.expertise_choice_grants(access, "class", cid):
            if _grant_applies_at(g, lv):
                out.append(("class", cid, g))
        if sub:
            for g in prof_q.expertise_choice_grants(access, "subclass", sub):
                if _grant_applies_at(g, lv):
                    out.append(("subclass", sub, g))
    for owner_kind, owner_id in _static_choice_owners(spec):
        for g in prof_q.expertise_choice_grants(access, owner_kind, owner_id):
            if _grant_applies_at(g, total_level):
                out.append((owner_kind, owner_id, g))
    return out


def expertise_choice(access, resolved, spec):
    """``(n, grants)`` for a build's expertise choices — ``n`` is the summed required count and
    ``grants`` the applicable grants (for pick validation). ``(0, [])`` when the build makes no
    expertise choice."""
    grants = _expertise_choice_grants_for_build(access, resolved, spec)
    return sum(g["choose_n"] or 0 for _ok, _oid, g in grants), grants


def expertise_pick_is_valid(access, resolved, spec, skill_id):
    """True when ``skill_id`` is a legal expertise pick for the build — a member of a grant's named
    pool when it names one, else any skill (the 'any already-proficient skill' mode; the proficiency
    prerequisite itself is a downstream concern that needs the full build). Validation only; no pool
    is emitted."""
    _n, grants = expertise_choice(access, resolved, spec)
    for _ok, _oid, g in grants:
        if prof_q.expertise_has_value_pool(access, g["id"]):
            if prof_q.expertise_value_in_grant(access, g["id"], skill_id):
                return True
        elif prof_q.is_skill(access, skill_id):
            return True
    return False


# --------------------------------------------------------------------------- feats
def ability_feat_slot_count(access, resolved):
    """Total ability-score-increase / feat slots the build has opened up, summed across its classes —
    each counted at its OWN class level, because the slots are a per-class progression (a multiclass
    build sums each class's slots). ``resolved`` is ``[(class_id, level, subclass_id), ...]``."""
    return sum(class_q.ability_feat_slots(access, cid, lv) for cid, lv, _sub in resolved)


def boon_slot_count(access, resolved):
    """Total top-tier boon slots the build has opened, summed across its classes — each counted at its
    OWN class level (a per-class progression). Distinct from :func:`ability_feat_slot_count`; a build
    that reaches the gating level offers this on top of its general ability-increase slots.
    ``resolved`` is ``[(class_id, level, subclass_id), ...]``."""
    return sum(class_q.top_tier_boon_slots(access, cid, lv) for cid, lv, _sub in resolved)


def weapon_mastery_choice(access, resolved):
    """``(n, weapon_ids)`` the build may fill with weapon-mastery picks: ``n`` is the sum of the
    weapon-mastery counts granted across the build's classes, each counted at its OWN class level
    (the allowance STACKS — a multiclass build adds each mastery-granting class's picks, since the
    multiclassing rules special-case only a few features and weapon mastery is not among them),
    capped at the pool size; ``weapon_ids`` is the masterable-weapon pool. ``(0, [])`` when no class
    grants a weapon-mastery feature. ``resolved`` is ``[(class_id, level, subclass_id), ...]``."""
    counts = [class_q.weapon_mastery_count(access, cid, lv) for cid, lv, _sub in resolved]
    n = sum(counts)
    if n <= 0:
        return 0, []
    pool = [r["id"] for r in catalog.masterable_weapons(access)]
    return min(n, len(pool)), pool


def feat_increase_allocation(access, feat_id, effective_scores):
    """The ability-score increase a chosen feat confers, as ``{"ability": ability_id, "amount": int}``,
    or None when the feat confers none. A feat with a fixed target set raises the highest-scoring of
    its allowed abilities; a from-any feat (the raw ability-score-increase itself) raises the build's
    highest ability. The amount is the grant's point budget, capped at its per-ability maximum, so the
    single-ability increase the choices model carries is always legal. Ties break to the lowest
    ability id for determinism. ``effective_scores`` is ability-id keyed (base + background boost)."""
    grant = feat_q.ability_increase_grant(access, feat_id)
    if grant is None or not grant["points"]:
        return None
    if grant["from_any"] or not grant["abilities"]:
        candidates = [r["id"] for r in catalog.list_abilities(access)]
    else:
        candidates = grant["abilities"]
    if not candidates:
        return None
    target = max(sorted(candidates), key=lambda aid: effective_scores.get(aid, 0))
    amount = grant["points"]
    if grant["max_per_ability"] is not None:
        amount = min(amount, grant["max_per_ability"])
    return {"ability": target, "amount": amount}


def increase_is_choosable(access, feat_id):
    """True when a feat's ability-score increase lets the model pick the target — a from-any increase
    (or one with no fixed target list). A fixed-target increase's ability is data-fixed and is not a
    model choice; a feat conferring no increase is not choosable either."""
    grant = feat_q.ability_increase_grant(access, feat_id)
    return bool(grant and grant["points"] and (grant["from_any"] or not grant["abilities"]))


def any_choosable_increase(access, feat_ids):
    """True if any feat in the pool offers a model-choosable ability-increase target — the grammar
    uses this to decide whether to expose the per-slot target field at all."""
    return any(increase_is_choosable(access, fid) for fid in feat_ids)


def increase_from_choice(access, feat_id, choice, effective_scores):
    """The ability-score increase a chosen ability-increase slot confers, honouring the model's
    target ``choice`` when the feat's increase is choosable and the pick is well-formed and legal,
    else falling back to the deterministic :func:`feat_increase_allocation`.

    ``choice`` is the model's per-slot pick: ``{"shape": "two", "ability": id}`` for a single-target
    +2 (returned as ``{"ability", "amount"}``), or ``{"shape": "split", "abilities": [id, id]}`` for
    a +1/+1 split across two distinct abilities (returned as a list of ``{"ability", "amount"}``).
    Targets are validated against the grant's allowed set (any ability for a from-any grant) and the
    split is only honoured when the grant's point budget and per-ability cap allow +1 to two
    abilities. An absent or illegal pick falls back to the heuristic, so the result is always legal
    by construction. Returns None when the feat confers no increase."""
    grant = feat_q.ability_increase_grant(access, feat_id)
    if grant is None or not grant["points"]:
        return None
    if not increase_is_choosable(access, feat_id):
        # A fixed-target increase's ability is data-fixed — the model has no say.
        return feat_increase_allocation(access, feat_id, effective_scores)
    candidates = grant["abilities"] or [r["id"] for r in catalog.list_abilities(access)]
    allowed = set(candidates)
    cap = grant["max_per_ability"]
    if isinstance(choice, dict):
        shape = choice.get("shape")
        if shape == "two":
            aid = choice.get("ability")
            if aid in allowed:
                amount = grant["points"] if cap is None else min(grant["points"], cap)
                return {"ability": aid, "amount": amount}
        elif shape == "split":
            abilities = choice.get("abilities")
            if (isinstance(abilities, list) and len(abilities) == 2
                    and len(set(abilities)) == 2 and set(abilities) <= allowed
                    and grant["points"] >= 2 and (cap is None or cap >= 1)):
                return [{"ability": aid, "amount": 1} for aid in abilities]
    return feat_increase_allocation(access, feat_id, effective_scores)


def any_repeatable(access, feat_ids):
    """True if any feat in the pool is repeatable — the grammar uses this to decide whether a
    ``uniqueItems`` constraint would wrongly ban repeating the raw ability-score-increase feat."""
    return any(feat_q.is_repeatable(access, fid) for fid in feat_ids)


def dedupe_slot_feats(access, feat_ids):
    """Drop duplicate NON-repeatable feats, preserving order: a non-repeatable feat may fill only one
    slot, while a repeatable feat (the raw ability-score-increase) may fill several. This backstops
    the grammar — JSON-schema ``uniqueItems`` can't express per-item repeatability, so uniqueness is
    enforced here rather than in the schema whenever the pool contains a repeatable feat."""
    out = []
    seen_non_repeatable = set()
    for fid in feat_ids:
        if feat_q.is_repeatable(access, fid):
            out.append(fid)
        elif fid not in seen_non_repeatable:
            seen_non_repeatable.add(fid)
            out.append(fid)
    return out


def eligible_feats(access, base_scores, boost, total_level, category="general"):
    """The feat ids a build may take in an ability-increase/feat slot — the feats in ``category``
    whose prerequisites the build meets. Only ability-minimum and character-level prerequisites are
    gated here (the two prerequisite kinds the DAL exposes as facts); richer kinds are left to the
    deriver. ``base_scores``/``boost`` are ability-id keyed; a prereq's effective score is the sum."""
    scores = dict(base_scores)
    for aid, amt in (boost or {}).items():
        scores[aid] = scores.get(aid, 0) + amt
    return [f["id"] for f in feat_q.list_feats(access, category=category)
            if _prereqs_met(access, f["id"], scores, total_level)]


def _prereqs_met(access, feat_id, scores, total_level):
    """AND across distinct ``any_of_group`` values, OR within a group — the grouping the DAL's raw
    prerequisite rows encode."""
    groups: dict = {}
    for r in feat_q.feat_prereqs(access, feat_id):
        groups.setdefault(r["any_of_group"], []).append(r)
    return all(any(_one_prereq_met(row, scores, total_level) for row in rows)
               for rows in groups.values())


def _one_prereq_met(row, scores, total_level):
    kind = row["kind"]
    if kind == "level":
        return total_level >= (row["min_level"] or 0)
    if kind == "ability":
        return scores.get(row["ability_id"], 0) >= (row["min_score"] or 0)
    # Prerequisite kinds the grammar does not gate (e.g. an armour-proficiency prereq) are left to
    # the deriver — treat them as met at grammar time rather than wrongly ban a feat.
    return True


# --------------------------------------------------------------------------- spells
def spell_pools(access, resolved):
    """``(cantrip_pool, leveled_pool)`` — spell ids the build's caster sources may select, or
    ``(None, None)`` for a non-caster. A class casts when its progression is not 'none'; a subclass
    casts via its declared spell-list class. Pools are the union across every caster source,
    deduplicated, in (level, id) order. ``resolved`` is ``[(class_id, level, subclass_id), ...]``."""
    sources = _caster_list_classes(access, resolved)
    if not sources:
        return None, None
    cantrips: list = []
    leveled: list = []
    seen_c: set = set()
    seen_l: set = set()
    for list_class in sources:
        for r in spell_q.class_spell_pool(access, list_class, level_min=0, level_max=0):
            if r["id"] not in seen_c:
                seen_c.add(r["id"])
                cantrips.append(r["id"])
        for r in spell_q.class_spell_pool(access, list_class, level_min=1):
            if r["id"] not in seen_l:
                seen_l.add(r["id"])
                leveled.append(r["id"])
    return cantrips, leveled


def _caster_list_classes(access, resolved):
    """The spell-list class ids the build draws spells from — a spellcasting class draws from its own
    list; a spellcasting subclass draws from its declared spell-list class."""
    out: list = []
    by_id = {r["id"]: r for r in class_q.list_classes(access)}
    for class_id, _level, subclass_id in resolved:
        row = by_id.get(class_id)
        progression = row["caster_progression"] if row else None
        if progression and progression != "none" and class_id not in out:
            out.append(class_id)
        if subclass_id:
            list_class = spell_q.subclass_spell_list_class(access, subclass_id)
            if list_class and list_class not in out:
                out.append(list_class)
    return out


# --------------------------------------------------------------------------- equipment
def equipment_bundles(access, owner_kind, owner_id):
    """The starting-equipment option bundles an owner (a class or a background) offers, as
    ``(id, label)`` pairs the grammar picks one from. Empty when the owner offers none."""
    return [(r["id"], r["label"])
            for r in equip_q.starting_equipment_options(access, owner_kind, owner_id)]


def resolve_bundle_items(access, option_id):
    """The concrete item specs inside a chosen bundle — one ``{id, name, quantity}`` per ``item``
    entry, its name resolved from the catalog. Non-item entries (gp / tool-category / focus /
    proficiency choices) are NOT resolved here: turning those into treasure, chosen tools, or foci is
    deriver work. An item whose name does not resolve is skipped rather than emitted nameless."""
    out: list = []
    for e in equip_q.starting_equipment_entries(access, option_id):
        if e["kind"] != "item" or not e["catalog_item_id"]:
            continue
        name = equip_q.item_name(access, e["catalog_item_id"])
        if name is None:
            continue
        out.append({"id": e["catalog_item_id"], "name": name, "quantity": e["quantity"] or 1})
    return out


def resolve_bundle_choice_items(access, option_id):
    """The equipment CHOICE-items inside a chosen bundle — the entries that carry no concrete catalog
    item and instead require the picker to choose one (a tool from a category, a form of a
    spellcasting focus, or the item matching a proficiency choice made elsewhere). Each is returned as
    a flaggable gap the completeness pass can surface, NOT a concrete inventory item and NOT an
    option pool:

    * ``{"kind": "tool_category", "tool_category": id}`` — a tool of the named category;
    * ``{"kind": "focus", "focus_type": id}``            — a form of the named focus type;
    * ``{"kind": "proficiency_choice"}``                 — the item matching the owner's tool-prof pick.

    The category / focus-type ids are the generic mechanic kind (data from the loaded ruleset), never
    the list of concrete items they could resolve to."""
    out = []
    for e in equip_q.starting_equipment_choice_entries(access, option_id):
        kind = e["kind"]
        if kind == "tool_category_choice":
            out.append({"kind": "tool_category", "tool_category": e["tool_category_id"]})
        elif kind == "focus_type_choice":
            out.append({"kind": "focus", "focus_type": e["focus_type_id"]})
        else:  # prof_choice_ref — the concrete item follows the owner's tool-proficiency choice
            out.append({"kind": "proficiency_choice"})
    return out


def resolve_bundle_gp(access, option_id):
    """The starting gold a chosen bundle grants — the sum of its ``gp`` line entries' amounts (0 when
    the bundle carries none). The reference model expresses starting wealth as a gp figure inside the
    equipment bundle, so this is the bundle's contribution to the character's starting treasure."""
    return sum(e["gp_amount"] or 0
               for e in equip_q.starting_equipment_entries(access, option_id)
               if e["kind"] == "gp")


def natural_slot(access, item_id):
    """The body slot a concrete item is worn/wielded in when first equipped, or None when it has no
    natural slot (gear, tools, consumables — these go to the backpack). A weapon is wielded in the
    main hand; worn armour occupies the armour slot; a shield occupies the shield slot. Grounded in
    the item's catalog kind + armour category — no game literals."""
    facts = equip_q.catalog_item_facts(access, item_id)
    if facts is None:
        return None
    kind = facts["kind"]
    if kind == "weapon":
        return "main_hand"
    if kind == "armor":
        armor = equip_q.armor_facts(access, item_id)
        category = armor["category_id"] if armor else None
        return "shield" if category == "shield" else "armor"
    return None
