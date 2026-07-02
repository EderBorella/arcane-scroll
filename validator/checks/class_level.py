"""Layer: class composition & level. Proficiency bonus vs total level; total level equals the sum of
class levels; each class's subclass declared only at/after its unlock level; and a multiclass character
meets each class's ability prerequisite. Collects every finding; never raises."""
from validator.report import Violation

LAYER = "class_level"


def check(sheet, rules):
    out = []
    ident = sheet.get("identity") or {}
    total = ident.get("total_level")
    classes = ident.get("classes", [])

    pb, expected = sheet.get("proficiency_bonus"), rules.proficiency_bonus(total)
    if expected is not None and pb != expected:
        out.append(Violation(LAYER, "proficiency_bonus",
                             f"proficiency bonus is {pb}; expected {expected} at level {total}",
                             expected, pb))

    # G1: total level must equal the sum of per-class levels.
    levels_sum = sum(c.get("level") or 0 for c in classes)
    if total is not None and levels_sum and total != levels_sum:
        out.append(Violation(LAYER, "total_level_mismatch",
                             f"total_level {total} != sum of class levels {levels_sum}", levels_sum, total))

    for c in classes:
        name, lvl, sub = c.get("class"), c.get("level", 0), c.get("subclass")
        unlock = rules.subclass_unlock(name)
        if unlock is None:
            continue
        if sub and lvl < unlock:
            out.append(Violation(LAYER, "subclass_too_early",
                                 f"{name} has a subclass at level {lvl}; it unlocks at level {unlock}",
                                 unlock, lvl))
        elif not sub and lvl >= unlock:
            out.append(Violation(LAYER, "subclass_missing",
                                 f"{name} (level {lvl}) has no subclass; one is required from level {unlock}",
                                 unlock, None))

    # G2: multiclassing requires 13+ in the primary ability of EVERY class ("or" ⇒ any of them).
    if len(classes) > 1:
        abils = sheet.get("abilities") or {}
        for c in classes:
            prim = rules.class_primary(c.get("class"))
            if not prim:
                continue
            scores = [(abils.get(a) or {}).get("final") for a in prim]
            scores = [s for s in scores if s is not None]
            if scores and max(scores) < 13:
                out.append(Violation(LAYER, "multiclass_prerequisite",
                                     f"{c.get('class')} needs 13+ in {prim} to multiclass; highest is {max(scores)}",
                                     13, max(scores)))
    return out
