"""The completeness manifest — the exhaustive, typed list of a build's outstanding choices.

Generation-side pass that turns the choice grammar (the count / gating helpers in ``options.py``)
plus a build's assembled ``choices`` into the ``manifest[]`` of the completeness report
(contract ``completeness-report:1``). One entry per unfilled / over-filled choice, ordered by
section (core -> grimoire -> inventory -> companion).

Two hard properties this module keeps:

* **FLAG-ONLY (liability).** An entry names the GENERIC resource kind to choose (``skill``,
  ``feat``, ``tool`` ...) plus the counts behind the gap. It NEVER carries an options pool or a
  source-specific name — the candidate menus (the reference source's curated lists) are read by
  ``options.py`` only for counts / single-id membership, never enumerated out here.
* **VALIDATOR-INDEPENDENT.** This module never reads the validator's findings. It re-derives the
  choice surface from the same DB facts the grammar bounds itself with, so the generation-side
  manifest and the validator's own under-fill signal agree WITHOUT sharing code (the two-layer
  doctrine).

``choice_key`` is a deterministic, readable ``section.path`` string (e.g. ``core.classes.0.subclass``)
built purely from the field's position — identical across stateless calls for the same field, so a
UI can track one choice's progress. No server state, no counters.
"""
from access.generator import classes as class_q
from engine.choices import options

# Section order the manifest is sorted by (mirrors the report contract's stated ordering).
_SECTION_ORDER = {"core": 0, "grimoire": 1, "inventory": 2, "companion": 3}

# The model-facing grammar fields (``build_pass1_grammar`` + ``build_equipment_grammar``) and how the
# manifest treats each. COVERED fields become a manifest entry when unfilled; EXCLUDED fields are
# deliberately NOT in the manifest — each with a logged reason (asserted by the exhaustiveness harness,
# T13), never a silent drop. The report contract's ``resource`` enum has no generic kind for a species
# sub-choice or a weapon-mastery pick, ``name`` is a free-text label, ``ability_increases`` is an
# optional per-slot target refinement with a deterministic fallback (never an unfilled gap), and an
# equipment bundle is a container pick whose unresolved sub-choices are flagged individually as
# ``tool`` / ``focus_item`` entries (see ``equipment_choices`` below).
COVERED_GRAMMAR_FIELDS = frozenset({
    "background_increase", "skills", "spells", "languages", "tools", "expertise", "feats", "boons",
})
EXCLUDED_GRAMMAR_FIELDS = {
    "name": "a free-text label, not a rule choice — the contract has no resource kind for it",
    "lineage": "a species lineage has no generic resource kind in the report contract",
    "species_variant": "a species variant axis has no generic resource kind in the report contract",
    "weapon_masteries": ("weapon mastery has no resource kind in the report contract; its "
                         "completeness is covered by the validator's weapon_mastery domain"),
    "ability_increases": ("an optional per-slot ability-target refinement with a deterministic "
                          "fallback — never an unfilled gap"),
    "equipment_class": ("a starting-equipment bundle is a container pick; its unresolved "
                        "choice-items are flagged individually as tool / focus_item entries"),
    "equipment_background": ("a starting-equipment bundle is a container pick; its unresolved "
                             "choice-items are flagged individually as tool / focus_item entries"),
}

# Manifest choices the builder emits that are NOT model-facing grammar fields: the subclass (a
# code-resolved pick, still a required choice) and the equipment choice-items (assembled downstream
# from a chosen bundle). Listed so the exhaustiveness harness can assert them explicitly.
NON_GRAMMAR_COVERED = ("subclass", "equipment_choices")

# Equipment choice-item kinds -> the generic resource kind + a neutral label. The kind ids the
# assembler carries (a tool category / a focus type) are the generic mechanic, never the list of
# concrete items they resolve to.
_EQUIP_CHOICE_RESOURCE = {
    "tool_category": ("tool", "choose a tool proficiency for a starting-equipment slot"),
    "proficiency_choice": ("tool", "choose the tool matching the build's tool-proficiency pick"),
    "focus": ("focus_item", "choose a spellcasting focus for a starting-equipment slot"),
}


def _choice_key(section: str, path: str) -> str:
    """The deterministic public id for a field — ``section`` joined to a dotted form of ``path``
    (``classes[0].subclass`` -> ``core.classes.0.subclass``). Pure function of the field's position:
    identical across stateless calls, no server state."""
    dotted = path.replace("[", ".").replace("]", "")
    return f"{section}.{dotted}"


def _entry(section: str, path: str, resource: str, kind: str, count: dict, description: str,
           status: str = "required") -> dict:
    return {
        "choice_key": _choice_key(section, path),
        "section": section,
        "path": path,
        "resource": resource,
        "type": kind,
        "count": count,
        "status": status,
        "description": description,
    }


def _count_entry(section: str, path: str, resource: str, required: int, filled: int,
                 description_kind: str, status: str = "required") -> dict | None:
    """A fixed-count choice entry (or None when the choice is exactly filled). Under-fill uses
    ``required``; over-fill uses ``max`` — matching the contract's count shape. ``description_kind``
    is the generic noun for the message (never a source-specific name)."""
    if filled == required:
        return None
    if filled < required:
        kind = "missing" if filled == 0 else "too_few"
        count = {"required": required, "filled": filled}
        verb = "choose" if kind == "missing" else "choose more"
        description = f"{verb} — {filled} of {required} {description_kind} chosen"
    else:
        kind = "too_many"
        count = {"max": required, "filled": filled}
        description = f"remove — {filled} {description_kind} chosen, at most {required} allowed"
    return _entry(section, path, resource, kind, count, description, status)


def _class_entries(choices: dict) -> list:
    raw = choices.get("classes")
    return raw if isinstance(raw, list) else []


def build_manifest(access, spec, resolved, choices: dict) -> list[dict]:
    """The typed completeness manifest for a build.

    ``access`` is a generator data-access handle; ``spec`` / ``resolved`` are the parsed build (as
    the grammar receives them); ``choices`` is the assembled selection object (possibly partial — a
    field left unfilled becomes a manifest gap). Every required count is re-derived from DB facts via
    ``options.py``; every filled count is read from ``choices``. Derivable fields need no entry.

    Ordered by section. FLAG-ONLY and VALIDATOR-INDEPENDENT (see the module docstring)."""
    choices = choices or {}
    entries: list[dict] = []
    if not resolved:            # a build always has >=1 class; guard the first-class reads below
        return entries

    # ---- core: subclass, one per class entry that has unlocked one but not chosen it ----------
    class_entries = _class_entries(choices)
    for i, (cid, level, _sub) in enumerate(resolved):
        unlock = class_q.subclass_unlock_level(access, cid)
        if unlock is None or level < unlock:
            continue  # no subclass to choose at this level — nothing to flag
        chosen = None
        if i < len(class_entries) and isinstance(class_entries[i], dict):
            chosen = class_entries[i].get("subclass")
        e = _count_entry("core", f"classes[{i}].subclass", "subclass", 1, 1 if chosen else 0,
                         "subclass")
        if e is not None:
            entries.append(e)

    # ---- core: background ability-boost distribution -----------------------------------------
    if spec.background and len(options.background_boost_options(access, spec.background)) >= 2:
        filled = 1 if choices.get("background_increase") else 0
        e = _count_entry("core", "abilities.background_increase", "ability_increase", 1, filled,
                         "ability-boost distribution")
        if e is not None:
            entries.append(e)

    # ---- core: skill proficiency picks (first class pool) ------------------------------------
    n_skill, _pool = options.skill_choice(access, resolved[0][0])
    if n_skill:
        e = _count_entry("core", "skills", "skill", n_skill, len(choices.get("skills") or []),
                         "skill proficiency")
        if e is not None:
            entries.append(e)

    # ---- core: expertise picks ----------------------------------------------------------------
    n_exp, _g = options.expertise_choice(access, resolved, spec)
    if n_exp:
        e = _count_entry("core", "skills.expertise", "expertise", n_exp,
                         len(choices.get("expertise") or []), "expertise")
        if e is not None:
            entries.append(e)

    # ---- core: tool proficiency picks --------------------------------------------------------
    n_tool, _g = options.tool_choice(access, resolved, spec)
    if n_tool:
        e = _count_entry("core", "proficiencies.tools", "tool", n_tool,
                         len(choices.get("tools") or []), "tool proficiency")
        if e is not None:
            entries.append(e)

    # ---- core: language picks -----------------------------------------------------------------
    n_lang, _g = options.language_choice(access, resolved, spec)
    if n_lang:
        e = _count_entry("core", "languages", "language", n_lang,
                         len(choices.get("languages") or []), "language")
        if e is not None:
            entries.append(e)

    # ---- core: ability-increase / feat slots + top-tier boon slots ---------------------------
    all_feats = choices.get("feats") or []
    boon_filled = sum(1 for f in all_feats if isinstance(f, dict) and f.get("source") == "boon")
    slot_filled = sum(1 for f in all_feats if not (isinstance(f, dict) and f.get("source") == "boon"))
    feat_slots = options.ability_feat_slot_count(access, resolved)
    if feat_slots:
        e = _count_entry("core", "feats", "feat", feat_slots, slot_filled,
                         "ability-increase/feat slot")
        if e is not None:
            entries.append(e)
    boon_slots = options.boon_slot_count(access, resolved)
    if boon_slots:
        e = _count_entry("core", "feats.boons", "feat", boon_slots, boon_filled, "boon slot")
        if e is not None:
            entries.append(e)

    # ---- grimoire: spell / cantrip selection (presence-only) ---------------------------------
    # The choice grammar bounds spells by pool, not by a hard count at pass-1 time (the known /
    # prepared budget is placed by the GRIMOIRE deriver downstream). So the manifest flags only a
    # caster that has picked NOTHING for a non-empty pool — a presence gap, not a count.
    cantrip_pool, leveled_pool = options.spell_pools(access, resolved)
    if cantrip_pool is not None:
        picked = choices.get("spells") or {}
        cantrips = picked.get("cantrips") or [] if isinstance(picked, dict) else []
        leveled = picked.get("spells") or [] if isinstance(picked, dict) else []
        if cantrip_pool and not cantrips:
            entries.append(_entry("grimoire", "cantrips", "cantrip", "missing", {"filled": 0},
                                  "choose at least one cantrip"))
        if leveled_pool and not leveled:
            entries.append(_entry("grimoire", "spells", "spell", "missing", {"filled": 0},
                                  "choose at least one spell"))

    # ---- inventory: unresolved equipment choice-items ----------------------------------------
    for j, item in enumerate(choices.get("equipment_choices") or []):
        if not isinstance(item, dict):
            continue
        resource, description = _EQUIP_CHOICE_RESOURCE.get(item.get("kind"),
                                                           ("tool", "resolve a starting-equipment choice"))
        entries.append(_entry("inventory", f"equipment_choices[{j}]", resource, "missing",
                              {"required": 1, "filled": 0}, description))

    entries.sort(key=lambda e: _SECTION_ORDER.get(e["section"], 99))
    return entries


def awaiting_choices(manifest: list[dict]) -> bool:
    """True iff the manifest holds at least one required entry — the report's ``awaiting_choices``
    flag. The caller folds this into the completeness report."""
    return any(e.get("status") == "required" for e in manifest)
