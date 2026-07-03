"""Layer: spellcasting. Leveled spells use the unified *prepared* model; every spell is real (on some
class list); spell slots (and pact slots) match what the caster classes grant; cantrip and prepared
counts match the class/level budget (subclass always-prepared grants are additive, not counted); no
spell exceeds the highest available slot level; and every subclass-granted spell is present + prepared.
Single-caster count checks are errors; multiclass counts are advisory (per-class attribution is
ambiguous on the sheet). Collects all findings; never raises."""
from validator.report import Violation, WARNING, ERROR

LAYER = "spellcasting"


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _slots_eq(a, b):
    """Compare two slot tables, ignoring zero / absent entries."""
    return {k: v for k, v in (a or {}).items() if v} == {k: v for k, v in (b or {}).items() if v}


def _slot_maxes(table):
    """The rule-checkable counts from a live slot table: {level: max} from the contract's
    {level: {max, remaining}} pools. `remaining` is live state, not rule-checkable, so it's ignored.
    Tolerates a bare int value too, so old-shape data still compares."""
    return {k: (v.get("max") if isinstance(v, dict) else v) for k, v in (table or {}).items()}


def _sum_or_none(rules_fn, caster_cls):
    """Sum a per-class budget across caster classes; None if any class's value is unknown."""
    total, seen = 0, False
    for c in caster_cls:
        v = rules_fn(c.get("class"), c.get("level") or 0)
        if v is None:
            return None
        total, seen = total + v, True
    return total if seen else None


def check(sheet, rules):
    out = []
    cb = sheet.get("spellcasting")
    if not cb:
        return out
    classes = (sheet.get("identity") or {}).get("classes") or []
    spells = cb.get("spells") or []
    sources = cb.get("sources") or {}

    def _non_class(s):
        """True if the spell comes from a declared non-class source (a feat / species / item — any
        source kind other than 'class'). Such a grant is fixed: it sits outside the class spell-list
        membership check and the cantrip/prepared budgets. A class source, or an unattributed spell (no
        source, or a source not declared in `sources`), is NOT excluded and keeps full checks.
        NOTE: this trusts the sheet's own source attribution — whether a feat/species really grants a
        given spell, and how many, is not independently verified here (that grounding is deferred)."""
        kind = sources.get(s.get("source"), {}).get("kind")
        return kind is not None and kind != "class"

    # Subclass always-prepared grants: must be present + prepared; collected (with class-feature
    # always-prepared spells) as additive grants that don't count against the prepared budget.
    subclass_granted = set()
    present = {_norm(s.get("name")) for s in spells}
    prepared_names = {_norm(s.get("name")) for s in spells if s.get("prepared")}
    for c in classes:
        for n in rules.subclass_grants(c.get("subclass"), c.get("level") or 0):
            subclass_granted.add(_norm(n))
            if _norm(n) not in present:
                out.append(Violation(LAYER, "subclass_spell_missing",
                                     f"subclass '{c.get('subclass')}' grants '{n}' as always-prepared; "
                                     f"it is not on the sheet", n, None))
            elif _norm(n) not in prepared_names:
                out.append(Violation(LAYER, "subclass_spell_not_prepared",
                                     f"subclass-granted spell '{n}' must be prepared", True, False))
    always = {_norm(n) for n in rules.always_prepared(classes)}
    excluded = subclass_granted | always      # additive grants — see prepared_count below

    # Real-spell membership — grants can sit off the base class lists, so include them and normalise
    # the comparison. The unified prepared model is skipped for a spellbook caster (its known pool may
    # legally hold unprepared leveled spells).
    base = rules.all_spells()
    known = {_norm(n) for n in base} | excluded
    spellbook = rules.has_spellbook(classes)
    for s in spells:
        name, lvl, prepared = s.get("name"), s.get("level") or 0, s.get("prepared")
        if lvl >= 1 and prepared is False and not spellbook and not _non_class(s):
            out.append(Violation(LAYER, "spell_not_prepared",
                                 f"leveled spell '{name}' is not prepared; casters use one prepared list",
                                 True, prepared))
        if base and _norm(name) not in known and not _non_class(s):
            out.append(Violation(LAYER, "unknown_spell",
                                 f"'{name}' is not on any class spell list", None, name))

    # Spell slots (single caster → own table; multiclass → combined table). Pact magic is separate.
    # Compare the rule-checkable slot counts (each pool's max) against what the caster classes grant.
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

    # Cantrip / prepared counts.
    caster_cls = [c for c in classes if rules.caster_type((c.get("class") or "").lower())]
    sev = WARNING if len(caster_cls) > 1 else ERROR

    exp_cantrips = _sum_or_none(rules.cantrips_known, caster_cls)
    n_cantrips = sum(1 for s in spells if (s.get("level") or 0) == 0 and not _non_class(s))
    if exp_cantrips is not None and n_cantrips != exp_cantrips:
        out.append(Violation(LAYER, "cantrip_count", f"{n_cantrips} cantrip(s); expected {exp_cantrips}",
                             exp_cantrips, n_cantrips, severity=sev))

    exp_prepared = _sum_or_none(rules.prepared_count, caster_cls)
    n_prepared = sum(1 for s in spells if (s.get("level") or 0) >= 1 and s.get("prepared")
                     and _norm(s.get("name")) not in excluded and not _non_class(s))
    if exp_prepared is not None and n_prepared != exp_prepared:
        out.append(Violation(LAYER, "prepared_count",
                             f"{n_prepared} prepared leveled spell(s) (excluding always-prepared grants); "
                             f"expected {exp_prepared}", exp_prepared, n_prepared, severity=sev))

    # Per-source ceiling for a non-class source: it can't be tagged with more spells than it declares
    # it grants. This bounds the source attribution the class-budget exclusion trusts (it does NOT
    # verify *which* spells the source grants — that grounding is deferred). Only sources that declare
    # a limit are checked; an undeclared limit can't be bounded, so it's skipped (no false positive).
    for src_id, src in sources.items():
        if src.get("kind") in (None, "class"):
            continue
        tagged = [s for s in spells if s.get("source") == src_id]
        cap_c = src.get("cantrips_known")
        if cap_c is not None:
            n = sum(1 for s in tagged if (s.get("level") or 0) == 0)
            if n > cap_c:
                out.append(Violation(LAYER, "source_cantrips_exceeded",
                                     f"source '{src_id}' has {n} cantrip(s) tagged but grants {cap_c}",
                                     cap_c, n))
        cap_p = src.get("prepared_limit")
        if cap_p is not None:
            n = sum(1 for s in tagged if (s.get("level") or 0) >= 1)
            if n > cap_p:
                out.append(Violation(LAYER, "source_spells_exceeded",
                                     f"source '{src_id}' has {n} leveled spell(s) tagged but grants {cap_p}",
                                     cap_p, n))

    # S17: a class source's DECLARED budgets (cantrips_known / prepared_limit) must equal what the
    # rules grant for that class at its level. Only class sources whose class the character has and
    # whose rule value is known are grounded (a prepared-caster budget the data doesn't table → skip).
    # The actual spell counts are already checked against the rules above, so a correct declared budget
    # also agrees with the actual counts.
    class_level = {(c.get("class") or "").lower(): c.get("level") or 0 for c in classes}
    for src_id, src in sources.items():
        if src.get("kind") != "class":
            continue
        cls_key = src_id.lower()
        lvl = class_level.get(cls_key)
        if lvl is None:
            continue
        exp_c, dec_c = rules.cantrips_known(cls_key, lvl), src.get("cantrips_known")
        if exp_c is not None and dec_c is not None and dec_c != exp_c:
            out.append(Violation(LAYER, "cantrips_known_mismatch",
                                 f"source '{src_id}' declares cantrips_known {dec_c}; the class grants "
                                 f"{exp_c} at level {lvl}", exp_c, dec_c))
        exp_p, dec_p = rules.prepared_count(cls_key, lvl), src.get("prepared_limit")
        if exp_p is not None and dec_p is not None and dec_p != exp_p:
            out.append(Violation(LAYER, "prepared_limit_mismatch",
                                 f"source '{src_id}' declares prepared_limit {dec_p}; the class grants "
                                 f"{exp_p} at level {lvl}", exp_p, dec_p))

    # No spell above the highest available slot level (pact casters may exceed it via Mystic Arcanum).
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
    return out
