"""Assemble the canonical ``choices`` structure — the DAL-grounded selection object the
derivation pipeline (``app.derivation.document.derive_document``) consumes — from a validated build
spec plus the model's grammar-constrained picks.

The choices carry canonical DB ids throughout (species / class / subclass / background / skill / feat
ids and ability-id-keyed score maps). The loaded ruleset's model shows in every seam: a *species* with no ability
bonus; the ability boost and the origin feat come from the *background*. Code-decided fields (the base
ability scores, the default boost, the resolved subclass, the equipment resolution) are injected here;
the model's picks refine the fields it is allowed to choose.
"""
from app.generation.choices import options


def assemble_choices(access, spec, resolved, picks, *, feat_slots=0, boon_slots=0):
    """The pass-1 choices object from the spec + the model's pass-1 picks. Equipment is added later
    (``apply_equipment``) so the two-pass seam stays intact; until then ``equipment`` is absent."""
    picks = picks or {}
    first_class = resolved[0][0]

    base_scores = options.base_ability_scores(access, first_class)
    background_increase = _background_increase(access, spec, picks)
    # Effective scores (base + background boost) — the baseline a feat's ability-increase allocation
    # reads to pick its best target, matching the scores the grammar gated feat eligibility on.
    effective_scores = dict(base_scores)
    for aid, amount in background_increase.items():
        effective_scores[aid] = effective_scores.get(aid, 0) + amount

    choices = {
        "character_id": spec.character_id,
        "character_name": picks.get("name") or spec.character_name,
        "species": spec.species,
        "lineage": _lineage(access, spec, picks),
        "species_variant": _species_variant(access, spec, picks),
        "classes": [{"class": cid, "level": lv, "subclass": sub} for cid, lv, sub in resolved],
        "background": spec.background,
        "ability_scores": base_scores,
        "background_increase": background_increase,
        "skills": list(picks.get("skills") or []),
        "feats": _feats(access, picks, feat_slots, boon_slots, effective_scores),
        "spells": _spells(picks),
        "weapon_masteries": _weapon_masteries(access, resolved, picks),
        "languages": [],
    }
    if spec.alignment is not None:
        choices["alignment"] = spec.alignment
    return choices


def _lineage(access, spec, picks):
    """The chosen lineage id, when the species offers lineages and the model picked a valid one; else
    None. Validated against the species's lineage set so a stray pick can't reach the deriver."""
    valid = set(options.lineage_options(access, spec.species))
    pick = picks.get("lineage")
    return pick if pick in valid else None


def _species_variant(access, spec, picks):
    """The chosen variant option NAME, when the species offers a variant axis and the model picked a
    valid option; else None. Validated against the species's option-name set (the sheet's
    ``species_variant`` field is name-keyed, matched by (species, axis, option_name))."""
    valid = set(options.variant_option_names(access, spec.species))
    pick = picks.get("species_variant")
    return pick if pick in valid else None


def _background_increase(access, spec, picks):
    """The +2/+1 (or +1/+1/+1) background ability boost, ability-id keyed. Uses the model's pick when
    it supplies a legal, well-formed shape (distinct targets for {2,1}) whose targets are all among the
    background's declared boost options, else the deterministic default (+2/+1 to the background's
    first two options)."""
    if not spec.background:
        return {}
    allowed = set(options.background_boost_options(access, spec.background))
    pick = picks.get("background_increase")
    if isinstance(pick, dict):
        shape = pick.get("shape")
        if shape == "two-one":
            p2, p1 = pick.get("plus_two"), pick.get("plus_one")
            if p2 and p1 and p2 != p1 and {p2, p1} <= allowed:
                return {p2: 2, p1: 1}
        elif shape == "one-one-one":
            abilities = pick.get("abilities")
            if (isinstance(abilities, list) and len(set(abilities)) == 3
                    and set(abilities) <= allowed):
                return {aid: 1 for aid in abilities}
    return options.default_background_boost(access, spec.background)


def _feats(access, picks, feat_slots, boon_slots, effective_scores):
    """Slot feats as ``[{feat: id, ability_increase?}, ...]`` — the general ability-increase/feat
    slots followed by the top-tier boon slots (each drawing from its own category). A slot is spent
    on a feat OR a raw ability-score increase (which is itself a feat), so each pick is a feat; when
    it confers an ability-score increase that increase is folded in as ``ability_increase`` (a
    DB-grounded allocation the CORE deriver adds to the ability's final).

    For a general slot spent on a raw (from-any) increase, the model's per-slot target pick from
    ``ability_increases`` decides which ability(ies) rise — a single-target +2 or a +1/+1 split —
    consumed positionally across the choosable feats; a slot without a supplied (or with an illegal)
    target falls back to the deterministic allocation. The ORIGIN feat is deliberately absent — CORE
    adds it from the background automatically, so listing it here would double-count it."""
    out = []
    if feat_slots > 0:
        increase_picks = list(picks.get("ability_increases") or [])
        ic_idx = 0
        for fid in options.dedupe_slot_feats(access, picks.get("feats") or []):
            entry = {"feat": fid}
            if options.increase_is_choosable(access, fid):
                choice = increase_picks[ic_idx] if ic_idx < len(increase_picks) else None
                ic_idx += 1
                increase = options.increase_from_choice(access, fid, choice, effective_scores)
            else:
                increase = options.feat_increase_allocation(access, fid, effective_scores)
            if increase is not None:
                entry["ability_increase"] = increase
            out.append(entry)
    if boon_slots > 0:
        # A top-tier boon draws from its own category; its increase (when any) uses the deterministic
        # allocation — the model chooses the boon, not its ability target.
        for fid in options.dedupe_slot_feats(access, picks.get("boons") or []):
            entry = {"feat": fid, "source": "boon"}
            increase = options.feat_increase_allocation(access, fid, effective_scores)
            if increase is not None:
                entry["ability_increase"] = increase
            out.append(entry)
    return out


def _weapon_masteries(access, resolved, picks):
    """The chosen masterable-weapon ids, validated against the build's masterable pool and capped at
    the count the build's weapon-mastery feature grants. Empty when the build gains no such feature
    or the model picked none — a stray or over-count pick is dropped rather than passed to the
    deriver, so the CORE ``weapon_masteries`` is legal by construction."""
    n, pool = options.weapon_mastery_choice(access, resolved)
    if n <= 0:
        return []
    allowed = set(pool)
    seen: set = set()
    out: list = []
    for wid in (picks.get("weapon_masteries") or []):
        if wid in allowed and wid not in seen:
            seen.add(wid)
            out.append(wid)
        if len(out) >= n:
            break
    return out


def _spells(picks):
    """The caster's spell picks, ``{cantrips: [ids], spells: [ids]}``. Consumed by the derivation
    pipeline: ``derive_document`` passes these into the GRIMOIRE deriver, which places them on the
    matching class source (as chosen cantrips / prepared spells) against the DB budgets."""
    sp = picks.get("spells")
    if not isinstance(sp, dict):
        return {"cantrips": [], "spells": []}
    return {"cantrips": list(sp.get("cantrips") or []), "spells": list(sp.get("spells") or [])}


def apply_equipment(access, spec, resolved, eq_picks, choices):
    """Fold the pass-2 equipment pick into ``choices``: resolve the chosen bundles' concrete item
    entries, assign each to its natural body slot (a weapon to the main hand, worn armour / a shield
    to their slots) with the remainder in ``equipment.backpack``, sum the bundles' starting gold into
    ``treasure``, and record the chosen bundle ids under ``starting_equipment`` for reference.

    The first item claiming a slot keeps it; a later item wanting an occupied slot (a second weapon)
    falls to the backpack. Items sharing a catalog id across bundles are merged into a single stacked
    record (their quantities summed) so the inventory never carries a duplicate item id.
    Tool-category / focus / proficiency-choice entries carry no concrete item and are not represented
    as inventory yet (a later card)."""
    eq_picks = eq_picks or {}
    bundles: dict = {}
    gp = 0
    # Merge the bundles' items by catalog id first (summing quantities), preserving first-seen order, so
    # the same item granted by two bundles becomes one stacked record rather than a duplicate id.
    merged: dict = {}
    order: list = []
    for owner_kind, field in (("class", "equipment_class"), ("background", "equipment_background")):
        option_id = eq_picks.get(field)
        if not option_id:
            continue
        bundles[owner_kind] = option_id
        gp += options.resolve_bundle_gp(access, option_id)
        for item in options.resolve_bundle_items(access, option_id):
            iid = item["id"]
            if iid in merged:
                merged[iid]["quantity"] = merged[iid].get("quantity", 1) + item.get("quantity", 1)
            else:
                merged[iid] = dict(item)
                order.append(iid)
    # Then assign each stacked item to its natural slot; the first to claim a slot keeps it and the
    # rest fall to the backpack.
    equipped: dict = {}
    backpack: list = []
    for iid in order:
        item = merged[iid]
        slot = options.natural_slot(access, iid)
        if slot and slot not in equipped:
            equipped[slot] = item
        else:
            backpack.append(item)
    if bundles:
        choices["starting_equipment"] = bundles
    choices["equipment"] = {"equipped": equipped, "backpack": backpack}
    choices["treasure"] = {"pp": 0, "gp": gp, "ep": 0, "sp": 0, "cp": 0}
    return choices
