"""Layer: spellcasting (v6). Each spell is attributed to a SOURCE (spell.source → a key in
spellcasting.sources) and held in a BUCKET (cantrip|prepared|always|known). Counting is per source and
therefore exact — multiclass included, no advisory downgrade: a class source's cantrip/prepared spells
count against that class's budget, while `always`/`known` are additive (subclass/feat/species grants and
spellbook entries). Every (name, source) is unique; a spell may repeat only under a different source.
Every spell is a catalog member. Spell/pact slots match the caster classes; no spell exceeds the top
available slot level (a pact caster's above-slot slotless casts excepted). Declared per-source budgets (S17) must match the rules.
Collects all findings; never raises.

INCREMENT 2 (not yet implemented here): bucket↔recovery coupling, `always`-grant-spec validation
(fixed list vs choose{from school|tag|list}), per-pick class-list constraint-checking, secondary_cast,
known-as-not-currently-castable."""
from validator.report import Violation, ERROR

LAYER = "spellcasting"


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _slots_eq(a, b):
    """Compare two slot tables, ignoring zero / absent entries."""
    return {k: v for k, v in (a or {}).items() if v} == {k: v for k, v in (b or {}).items() if v}


def _slot_maxes(table):
    """The rule-checkable counts from a live slot table: {level: max} from {level: {max, remaining}}
    pools. `remaining` is live state, not rule-checkable. Tolerates a bare int value too."""
    return {k: (v.get("max") if isinstance(v, dict) else v) for k, v in (table or {}).items()}


def check(sheet, rules):
    out = []
    cb = sheet.get("spellcasting")
    if not cb:
        return out
    classes = (sheet.get("identity") or {}).get("classes") or []
    spells = cb.get("spells") or []
    sources = cb.get("sources") or {}

    # (name, source) uniqueness — a spell may repeat only under a DIFFERENT source (its own ability/DC).
    seen = set()
    for s in spells:
        key = (_norm(s.get("name")), _norm(s.get("source")))
        if key in seen:
            out.append(Violation(LAYER, "duplicate_spell",
                                 f"'{s.get('name')}' from source '{s.get('source')}' is listed more than once",
                                 None, s.get("name")))
        seen.add(key)

    # Source resolution — every spell's source must be declared in spellcasting.sources.
    for s in spells:
        src = s.get("source")
        if src is not None and src not in sources:
            out.append(Violation(LAYER, "unknown_source",
                                 f"spell '{s.get('name')}' names source '{src}' not declared in "
                                 f"spellcasting.sources", None, src))

    # Catalog membership — every spell must be a real catalogued spell (skipped when no catalog loaded).
    for s in spells:
        if rules.is_catalog_spell(s.get("name")) is False:
            out.append(Violation(LAYER, "unknown_spell", f"'{s.get('name')}' is not in the spell catalog",
                                 None, s.get("name")))

    # Per-pick class-list constraint: a CHOSEN spell (cantrip/prepared/known) attributed to a CLASS source
    # must be on that class's spell list. `always` grants are exempt — they are validated against the
    # granting source's grant spec. Skipped when the spell isn't catalogued (already → unknown_spell) or no
    # catalog is loaded (spell_on_class_list → None).
    class_ids = {_norm(c.get("class")) for c in classes}
    for s in spells:
        if s.get("bucket") not in ("cantrip", "prepared", "known"):
            continue
        src = s.get("source")
        if _norm(src) not in class_ids:
            continue
        if rules.spell_on_class_list(s.get("name"), src) is False:
            out.append(Violation(LAYER, "spell_not_on_class_list",
                                 f"'{s.get('name')}' ({s.get('bucket')}) is not on the '{src}' spell list",
                                 src, s.get("name")))

    # `always`-grant validation: an `always` spell must be justified by its source's grant spec — a fixed
    # grant, or a valid choose{from: school|tag|list} pick (checked against the spell catalog). Only sources
    # that HAVE a grant record are checked; an ungranted source can't be validated, so it's skipped (no
    # false positive). Level-scaling of grants is a later slice.
    total_level = sum((c.get("level") or 0) for c in classes) or ((sheet.get("identity") or {}).get("total_level") or 0)

    def _applicable_level(rec, source_id):
        """The level to gate a source's grants by — a subclass's parent-class level, else total character level."""
        if (rec or {}).get("kind") == "subclass":
            parent = _norm(rec.get("parent_class"))
            for c in classes:
                if _norm(c.get("class")) == parent or _norm(c.get("subclass")) == _norm(source_id):
                    return c.get("level") or 0
            return 0
        return total_level

    def _applicable_entries(rec, level):
        return [gr for gr in (rec.get("grants") or []) if (gr.get("gained_at") or {}).get("level", 1) <= level]

    def _resolve_n(choose, level):
        """The count a choose{} grants, or None if it uses an unresolvable scaling token."""
        n = (choose or {}).get("n")
        if isinstance(n, int):
            return n
        if n == "proficiency_bonus":
            return rules.proficiency_bonus(level)
        return None

    def _satisfies(name, choose, variant=None):
        frm = (choose or {}).get("from") or {}
        typ, val = frm.get("type"), frm.get("value") or []
        want_lvl = frm.get("spell_level")
        if want_lvl not in (None, "any", "any_available") and rules.spell_catalog_level(name) != want_lvl:
            return False
        if typ == "school":
            return (rules.spell_catalog_school(name) or "").lower() in [str(v).lower() for v in val]
        if typ == "tag":
            return bool(rules.spell_catalog_ritual(name)) if "ritual" in [str(v).lower() for v in val] else False
        if typ == "list":
            allowed = [variant] if variant else val         # a repeatable-feat variant narrows to its chosen list
            return any(rules.spell_on_class_list(name, c) for c in allowed)
        return False

    # `always`-grant validation, LEVEL-GATED to the grants the source actually gives at this level.
    for s in spells:
        if s.get("bucket") != "always":
            continue
        g, variant = rules.resolve_source(s.get("source"))   # resolves repeatable-feat instances too
        if not g:
            continue
        entries = _applicable_entries(g, _applicable_level(g, s.get("source")))
        fixed = {_norm(n) for gr in entries for n in ((gr.get("spec") or {}).get("fixed") or [])}
        name = s.get("name")
        if _norm(name) in fixed:
            continue
        if any(_satisfies(name, (gr.get("spec") or {}).get("choose"), variant) for gr in entries
               if (gr.get("spec") or {}).get("choose")):
            continue
        out.append(Violation(LAYER, "always_spell_not_granted",
                             f"'{name}' is tagged as an always-prepared grant from '{s.get('source')}', "
                             f"but that source does not grant it", s.get("source"), name))

    # Grant COUNT per always-source (level-gated): the number of always grants must equal what the source
    # gives at this level. Skipped for a source with an unresolvable scaling token (no false positive).
    always_count = {}
    for s in spells:
        if s.get("bucket") == "always" and s.get("source"):
            always_count[s.get("source")] = always_count.get(s.get("source"), 0) + 1
    for src_id, actual in always_count.items():
        g, _v = rules.resolve_source(src_id)
        if not g:
            continue
        lvl = _applicable_level(g, src_id)
        expected, unresolvable = 0, False
        for gr in _applicable_entries(g, lvl):
            spec = gr.get("spec") or {}
            expected += len(spec.get("fixed") or [])
            if spec.get("choose"):
                n = _resolve_n(spec["choose"], lvl)
                if n is None:
                    unresolvable = True
                else:
                    expected += n
        if not unresolvable and actual != expected:
            out.append(Violation(LAYER, "grant_count_mismatch",
                                 f"source '{src_id}' has {actual} always-prepared grant(s); expected {expected} "
                                 f"at this level", expected, actual))

    # bucket ↔ recovery coupling — catch contradictory combinations (independent axes must still agree).
    for s in spells:
        b, r = s.get("bucket"), s.get("recovery")
        if (b == "cantrip" and r in ("spell_slot", "pact_slot", "slotless_per_rest", "ritual_only")) \
                or (b == "known" and r is not None) \
                or (b == "prepared" and r == "at_will"):
            out.append(Violation(LAYER, "bucket_recovery_mismatch",
                                 f"'{s.get('name')}': bucket '{b}' is incompatible with recovery '{r}'", b, r))

    # Per-source counting (EXACT). For each caster CLASS source, count the cantrip/prepared buckets
    # attributed to it against that class's budget. `always`/`known` are additive and never counted.
    for c in classes:
        cid = (c.get("class") or "").lower()
        lvl = c.get("level") or 0
        if not rules.caster_type(cid):
            continue
        attributed = [s for s in spells if _norm(s.get("source")) == _norm(cid)]
        exp_c = rules.cantrips_known(cid, lvl)
        if exp_c is not None:
            n = sum(1 for s in attributed if s.get("bucket") == "cantrip")
            if n != exp_c:
                out.append(Violation(LAYER, "cantrip_count",
                                     f"class '{cid}': {n} cantrip(s); expected {exp_c}", exp_c, n))
        exp_p = rules.prepared_count(cid, lvl)
        if exp_p is not None:
            n = sum(1 for s in attributed if s.get("bucket") == "prepared")
            if n != exp_p:
                out.append(Violation(LAYER, "prepared_count",
                                     f"class '{cid}': {n} prepared leveled spell(s); expected {exp_p}", exp_p, n))

    # Spell slots (single caster → own table; multiclass → combined). Pact magic is separate.
    expected = rules.expected_slots(classes)
    got_slots = _slot_maxes(cb.get("spell_slots"))
    if expected is not None and not _slots_eq(expected, got_slots):
        out.append(Violation(LAYER, "spell_slots_mismatch",
                             f"spell slots {got_slots} != expected {expected}", expected, got_slots))
    exp_pact = rules.expected_pact(classes)
    got_pact = _slot_maxes(cb.get("pact_slots"))
    if exp_pact is not None and not _slots_eq(exp_pact, got_pact):
        out.append(Violation(LAYER, "pact_slots_mismatch",
                             f"pact slots {got_pact} != expected {exp_pact}", exp_pact, got_pact))

    # No spell above the highest available slot level (a pact caster may exceed it via above-slot slotless casts).
    max_level = max([int(k) for k, v in (expected or {}).items() if v]
                    + [int(k) for k, v in (exp_pact or {}).items() if v]
                    + [rules.arcanum_max_level(classes), 0])
    if max_level:
        for s in spells:
            lvl = s.get("level") or 0
            if lvl > max_level:
                out.append(Violation(LAYER, "spell_level_too_high",
                                     f"'{s.get('name')}' is level {lvl}; highest available slot is {max_level}",
                                     max_level, lvl))

    # S17: a class source's DECLARED budgets must equal what the rules grant for that class at its level.
    class_level = {(c.get("class") or "").lower(): c.get("level") or 0 for c in classes}
    for src_id, src in sources.items():
        if src.get("kind") != "class":
            continue
        lvl = class_level.get(src_id.lower())
        if lvl is None:
            continue
        exp_c, dec_c = rules.cantrips_known(src_id.lower(), lvl), src.get("cantrips_known")
        if exp_c is not None and dec_c is not None and dec_c != exp_c:
            out.append(Violation(LAYER, "cantrips_known_mismatch",
                                 f"source '{src_id}' declares cantrips_known {dec_c}; the class grants "
                                 f"{exp_c} at level {lvl}", exp_c, dec_c))
        exp_p, dec_p = rules.prepared_count(src_id.lower(), lvl), src.get("prepared_limit")
        if exp_p is not None and dec_p is not None and dec_p != exp_p:
            out.append(Violation(LAYER, "prepared_limit_mismatch",
                                 f"source '{src_id}' declares prepared_limit {dec_p}; the class grants "
                                 f"{exp_p} at level {lvl}", exp_p, dec_p))

    return out
