"""Layer: class composition & level. Proficiency bonus vs total level, and each class's subclass
declared only at/after its unlock level. Collects every finding; never raises."""
from validator.report import Violation

LAYER = "class_level"


def check(sheet, rules):
    out = []
    ident = sheet.get("identity") or {}
    total = ident.get("total_level")

    pb, expected = sheet.get("proficiency_bonus"), rules.proficiency_bonus(total)
    if expected is not None and pb != expected:
        out.append(Violation(LAYER, "proficiency_bonus",
                             f"proficiency bonus is {pb}; expected {expected} at level {total}",
                             expected, pb))

    for c in ident.get("classes", []):
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
    return out
