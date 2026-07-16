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


# --------------------------------------------------------------------------- feats
def ability_feat_slot_count(access, resolved):
    """Total ability-score-increase / feat slots the build has opened up, summed across its classes —
    each counted at its OWN class level, because the slots are a per-class progression (a multiclass
    build sums each class's slots). ``resolved`` is ``[(class_id, level, subclass_id), ...]``."""
    return sum(class_q.ability_feat_slots(access, cid, lv) for cid, lv, _sub in resolved)


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
