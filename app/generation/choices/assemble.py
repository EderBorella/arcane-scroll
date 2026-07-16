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


def assemble_choices(access, spec, resolved, picks, *, feat_slots=0):
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
        "feats": _feats(access, picks, feat_slots, effective_scores),
        "spells": _spells(picks),
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


def _feats(access, picks, feat_slots, effective_scores):
    """Class/level-slot feats as ``[{feat: id, ability_increase?}, ...]``. A slot is spent on a general
    feat OR a raw ability-score increase (which is itself a general feat), so each pick is a general
    feat; when that feat confers an ability-score increase it is folded in as ``ability_increase`` (a
    DB-grounded allocation the CORE deriver adds to the ability's final). The ORIGIN feat is
    deliberately absent — CORE adds it from the background automatically, so listing it here would
    double-count it."""
    if feat_slots <= 0:
        return []
    out = []
    for fid in options.dedupe_slot_feats(access, picks.get("feats") or []):
        entry = {"feat": fid}
        increase = options.feat_increase_allocation(access, fid, effective_scores)
        if increase is not None:
            entry["ability_increase"] = increase
        out.append(entry)
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
    entries into ``equipment.backpack`` (what the INVENTORY assembly consumes) and record the chosen
    bundle ids under ``starting_equipment`` for reference. gp / tool-category / focus / proficiency
    entries are NOT turned into treasure, tools, or foci here — that is deriver work (Phase-5)."""
    eq_picks = eq_picks or {}
    bundles: dict = {}
    backpack: list = []
    for owner_kind, field in (("class", "equipment_class"), ("background", "equipment_background")):
        option_id = eq_picks.get(field)
        if option_id:
            bundles[owner_kind] = option_id
            backpack.extend(options.resolve_bundle_items(access, option_id))
    if bundles:
        choices["starting_equipment"] = bundles
    choices["equipment"] = {"equipped": {}, "backpack": backpack}
    return choices
