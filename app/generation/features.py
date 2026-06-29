"""Feature-choice descriptors — the "expanded contract" the model fills on top of the base sheet.

A character's (class, subclass, level) — and race — unlock specific picks: fighting style, expertise,
maneuvers, invocations, metamagic, totems, ancestry, third-caster spells, feats/ASI, race options, …
Each is a `{field, enum, n}` descriptor — the gating and counts are mechanics (code), the value lists
come from the catalog by neutral key. The sheet generator merges these into the per-request grammar
and fits them in repair. Single-pick choices (`n == 1`) are a string; multi-pick are a deduped array.

(Applying a feat's or ASI's mechanical effect is derivation-engine work, like subclass effects.)"""
from app.generation import helpers as H


# ── count progressions ────────────────────────────────────────────────────────
def _maneuvers_n(lv):       return 3 + (2 if lv >= 7 else 0) + (2 if lv >= 10 else 0) + (2 if lv >= 15 else 0)
def _metamagic_n(lv):       return 2 + (1 if lv >= 10 else 0) + (1 if lv >= 17 else 0)
def _disciplines_n(lv):     return 1 + (1 if lv >= 6 else 0) + (1 if lv >= 11 else 0) + (1 if lv >= 17 else 0)
def _favored_enemy_n(lv):   return 1 + (1 if lv >= 6 else 0) + (1 if lv >= 14 else 0)
def _favored_terrain_n(lv): return 1 + (1 if lv >= 6 else 0) + (1 if lv >= 10 else 0)


def _invocations_n(lv):
    for threshold, count in [(18, 8), (15, 7), (12, 6), (9, 5), (7, 4), (5, 3), (2, 2)]:
        if lv >= threshold:
            return count
    return 0


def _expertise_count(ci, lv):
    """Proficient skills a class doubles (Rogue: 2 @L1 +2 @L6; Bard: 2 @L3 +2 @L10)."""
    if ci == "rogue": return (2 if lv >= 1 else 0) + (2 if lv >= 6 else 0)
    if ci == "bard":  return (2 if lv >= 3 else 0) + (2 if lv >= 10 else 0)
    return 0


# third-caster (Eldritch Knight / Arcane Trickster) progression
def _third_max_spell_lv(lv): return 1 if lv < 7 else 2 if lv < 13 else 3 if lv < 19 else 4
def _third_cantrips_n(lv):   return 3 if lv >= 10 else 2


def _third_spells_n(lv):
    n = 3
    for threshold in (7, 8, 11, 13, 14, 16, 19, 20):
        if lv >= threshold:
            n += 1
    return n


def _fighting_style_classes(cat, classes):
    """Classes (from the request) whose level grants a fighting style."""
    levels, styles = cat.get("fighting_style_level", {}), cat.get("fighting_styles", {})
    return [ci for ci, lv, _ in classes if ci in styles and lv >= levels.get(ci, 99)]


def _asi_slots(cat, ci, lv):
    """Feat/ASI slots a class has reached by `lv` (class-specific schedule, else the default)."""
    levels = cat.get("asi_levels", {}).get(ci) or cat.get("asi_default_levels")
    return sum(1 for t in levels if lv >= t)


def capabilities(cat, classes) -> set:
    """The character's combat/casting capabilities — union over classes (multiclass) + subclasses.
    `caster` = any spellcasting class or caster subclass (EK/AT); `martial` = any martial class or
    martial subclass (College of Valor). Used to ban feats that would be dead for this character."""
    caster_cl = set(cat.get("known_casters", [])) | set(cat.get("prepared_casters", []))
    martial_cl = set(cat.get("martial_classes", []))
    sub_caps = cat.get("subclass_capabilities", {})
    caps = set()
    for ci, lv, sub in classes:
        if ci in caster_cl:
            caps.add("caster")
        if ci in martial_cl:
            caps.add("martial")
        if sub:
            caps |= set(sub_caps.get(H._norm(sub), []))
    return caps


_ARMOR_CATEGORIES = {"light-armor", "medium-armor", "heavy-armor"}


def _armor_proficiencies(cat, classes) -> set:
    """Armour-category proficiencies from the character's classes (`all-armor` expands to all three).
    Class-granted only — racial armour training is a rare edge not covered here."""
    profs = set()
    for ci, _, _ in classes:
        for p in (cat.record("classes", ci) or {}).get("proficiencies", []):
            idx = p.get("index", "")
            if idx == "all-armor":
                profs |= _ARMOR_CATEGORIES
            elif idx in _ARMOR_CATEGORIES:
                profs.add(idx)
    return profs


def eligible_feats(cat, classes, race=None) -> list:
    """Feats this character can actually use — drop ones whose prerequisite it doesn't meet:
    capability (caster/martial), ability-score minimum, or armour proficiency. Ability scores are the
    pre-call values (combined-priority array + racial bonuses)."""
    caps = capabilities(cat, classes)
    attrs = cat.get("feat_attributes", {})
    array = H.ability_assignment(cat, classes)
    scores = {ab: array[ab] + H.race_bonus(cat, race, ab) for ab in array}
    armor = _armor_proficiencies(cat, classes)
    out = []
    for f in cat.get("feats"):
        a = attrs.get(f, {})
        if (a.get("requires") or "any") not in (caps | {"any"}):
            continue
        if any(scores.get(ab, 0) < mn for ab, mn in a.get("min_ability", {}).items()):
            continue
        rp = a.get("requires_proficiency")
        if rp and rp not in armor:
            continue
        out.append(f)
    return out


# ── the registry ──────────────────────────────────────────────────────────────
def descriptors(cat, classes, race=None):
    """classes: [(ci, lv, subclass_or_None)]. Ordered [{field, enum, n}] for every choice granted."""
    out = []

    def add(field, enum, n):
        enum = list(enum or [])
        n = min(n, len(enum))                # can't grant more picks than the pool holds
        if n > 0:
            out.append({"field": field, "enum": enum, "n": n})

    # fighting style — one pick per granting class
    granting = _fighting_style_classes(cat, classes)
    if granting:
        styles = cat.get("fighting_styles", {})
        add("fighting_style", sorted(set().union(*[set(styles[ci]) for ci in granting])), len(granting))

    # expertise — picked from the primary class's skill list (repair narrows to the chosen skills)
    exp = sum(_expertise_count(ci, lv) for ci, lv, _ in classes)
    if exp:
        _, skill_idx = H.class_skill_grant(cat, classes[0][0])
        skills = H.skill_names(cat, skill_idx)
        add("expertise", skills, min(exp, len(skills)))

    # subclass feature oddities — gated per (class, subclass, level)
    for ci, lv, subclass in classes:
        sub = H._norm(subclass or "")
        if ci == "sorcerer":
            add("metamagic", cat.get("metamagic"), _metamagic_n(lv) if lv >= 3 else 0)
            if "draconic" in sub:
                add("draconic_ancestry", cat.get("draconic_ancestry"), 1)
        elif ci == "warlock":
            add("pact_boon", cat.get("pact_boon"), 1 if lv >= 3 else 0)
            prereqs = cat.get("invocation_prereqs", {})       # offer only level-eligible invocations
            invs = [i for i in cat.get("invocations") if lv >= prereqs.get(i, {}).get("min_level", 1)]
            add("invocations", invs, _invocations_n(lv))
        elif ci == "ranger":
            add("favored_enemy", cat.get("creature_types"), _favored_enemy_n(lv))
            add("favored_terrain", cat.get("terrain"), _favored_terrain_n(lv))
            if "hunter" in sub:
                add("hunters_prey", cat.get("hunters_prey"), 1 if lv >= 3 else 0)
                add("defensive_tactics", cat.get("defensive_tactics"), 1 if lv >= 7 else 0)
            elif "beast" in sub:
                add("animal_companion", cat.get("beasts"), 1 if lv >= 3 else 0)
        elif ci == "barbarian" and "totem" in sub:
            add("totem_spirit", cat.get("totem"), 1 if lv >= 3 else 0)
            add("totem_aspect", cat.get("totem"), 1 if lv >= 6 else 0)
            add("totem_attunement", cat.get("totem"), 1 if lv >= 14 else 0)
        elif ci == "fighter":
            if "battlemaster" in sub:
                add("maneuvers", cat.get("maneuvers"), _maneuvers_n(lv) if lv >= 3 else 0)
            elif "eldritch" in sub and lv >= 3:
                add("ek_cantrips", H.school_spells(cat, "wizard", None, 0, 0), _third_cantrips_n(lv))
                add("ek_spells", H.school_spells(cat, "wizard", {"abjuration", "evocation"}, 1, _third_max_spell_lv(lv)),
                    _third_spells_n(lv))
        elif ci == "rogue" and "arcanetrickster" in sub and lv >= 3:
            add("at_cantrips", H.school_spells(cat, "wizard", None, 0, 0), _third_cantrips_n(lv))
            add("at_spells", H.school_spells(cat, "wizard", {"enchantment", "illusion"}, 1, _third_max_spell_lv(lv)),
                _third_spells_n(lv))
        elif ci == "monk" and "four" in sub:
            add("elemental_disciplines", cat.get("elemental_disciplines"), _disciplines_n(lv))
        elif ci == "druid" and "land" in sub and lv >= 2:
            add("land_type", cat.get("land_type"), 1)
            add("bonus_cantrip", H.school_spells(cat, "druid", None, 0, 0), 1)
        elif ci == "bard" and "lore" in sub:
            add("bonus_skills", H.all_skill_names(cat), 3 if lv >= 3 else 0)
            add("magical_secrets", H.school_spells(cat, None, None, 1, H.max_spell_level(cat, "bard", lv)),
                2 if lv >= 6 else 0)
        elif ci == "cleric":
            if "knowledge" in sub:
                add("knowledge_skills", cat.get("knowledge_skills"), 2)
            elif "nature" in sub:
                add("nature_cantrip", H.school_spells(cat, "druid", None, 0, 0), 1)
                add("nature_skill", cat.get("nature_skills"), 1)

    # feat / ASI (character-level). 1 slot: the model picks a feat OR an ability bump. 2+ slots: code
    # reserves one slot for an ASI, the model picks the other (N-1) as feats.
    slots = sum(_asi_slots(cat, ci, lv) for ci, lv, _ in classes)
    feats = eligible_feats(cat, classes, race)            # ban feats this character can't use
    if slots == 1:
        bumps = [f"Ability Score Improvement: {label}" for label in cat.get("asi_label", {}).values()]
        add("feat", feats + bumps, 1)
    elif slots >= 2:
        add("feat", feats, slots - 1)

    # race-level choices
    r = H._norm(race or "")
    if "dragonborn" in r:
        add("dragonborn_ancestry", cat.get("draconic_ancestry"), 1)
    if "highelf" in r:
        add("high_elf_cantrip", H.school_spells(cat, "wizard", None, 0, 0), 1)
    if "halfelf" in r:
        add("half_elf_skills", H.all_skill_names(cat), 2)
    return out


# ── consumers (grammar + repair) ──────────────────────────────────────────────
def feature_props(cat, classes, race=None):
    """Schema props (+ required names): single-pick → string enum, multi-pick → unique array."""
    props, req = {}, []
    for d in descriptors(cat, classes, race):
        if d["n"] == 1:
            props[d["field"]] = {"enum": d["enum"]}
        else:
            props[d["field"]] = {"type": "array", "items": {"enum": d["enum"]},
                                 "minItems": d["n"], "maxItems": d["n"], "uniqueItems": True}
        req.append(d["field"])
    return props, req


def _invocation_ok(prereqs, inv, wl_level, pact, has_eb) -> bool:
    """Whether a warlock meeting (level, chosen pact, has-Eldritch-Blast) qualifies for an invocation."""
    p = prereqs.get(inv, {})
    if wl_level < p.get("min_level", 1):
        return False
    if p.get("requires_pact") and p["requires_pact"] not in pact:
        return False
    if p.get("requires_eldritch_blast") and not has_eb:
        return False
    return True


def _repair_invocations(cat, ch, classes):
    """Drop invocations whose pact/Eldritch-Blast prereq the chosen build doesn't meet (these depend
    on pact_boon + cantrips, picked in the same call, so they can't be pre-banned), re-padding from
    the invocations the build does qualify for."""
    if "invocations" not in ch:
        return
    prereqs = cat.get("invocation_prereqs", {})
    pact = H._norm(ch.get("pact_boon", ""))
    has_eb = any(H._norm(c) == H._norm("Eldritch Blast")
                 for c in (ch.get("spell_choices") or {}).get("cantrips", []))
    wl = max((lv for ci, lv, _ in classes if ci == "warlock"), default=0)
    n = len(ch["invocations"])
    eligible = [i for i in cat.get("invocations") if _invocation_ok(prereqs, i, wl, pact, has_eb)]
    kept = [i for i in ch["invocations"] if _invocation_ok(prereqs, i, wl, pact, has_eb)]
    ch["invocations"] = H._dedup_pad(kept, eligible, n)


def repair_features(cat, ch, classes, race=None):
    """Fit each feature field to its enum/count (a grammar can't enforce uniqueness). Expertise must
    double *chosen* skills, so it's fit against `skill_choices` rather than the whole class list.
    Invocations get an extra cross-field pass (pact / Eldritch Blast prereqs)."""
    for d in descriptors(cat, classes, race):
        f = d["field"]
        pool = ch.get("skill_choices", []) if f == "expertise" else d["enum"]
        # synthesize a value for a field the model omitted entirely (grammars can't guarantee
        # presence under truncation) — pad from the granted pool rather than leaving it missing
        raw = ch.get(f, [])
        cur = [raw] if isinstance(raw, str) else list(raw or [])
        fit = H._dedup_pad(cur, pool, d["n"])
        if d["n"] == 1:
            if fit:
                ch[f] = fit[0]
        else:
            ch[f] = fit
    _repair_invocations(cat, ch, classes)
    return ch
