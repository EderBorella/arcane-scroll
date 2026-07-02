"""Layer: masteries. Every weapon in the character's weapon_masteries list actually has a mastery
property to master, and — for a single-class character whose class grants the feature — the number
mastered matches the class's Weapon Mastery count at its level. Multiclass/untracked counts are
advisory (per-class attribution is ambiguous, and other sources can grant the feature). Grounded in
the weapon and per-class count data."""
from validator.report import Violation, WARNING

LAYER = "masteries"


def check(sheet, rules):
    out = []
    mastered = sheet.get("weapon_masteries") or []

    for w in mastered:
        if rules.weapon_has_mastery(w) is False:      # None = weapon unknown → can't judge
            out.append(Violation(LAYER, "weapon_has_no_mastery",
                                 f"'{w}' has no mastery property to master", None, w))

    classes = (sheet.get("identity") or {}).get("classes") or []
    tracked = [(c.get("class"), rules.weapon_mastery_count(c.get("class"), c.get("level") or 0))
               for c in classes]
    tracked = [(cid, n) for cid, n in tracked if n is not None]

    if len(classes) == 1 and len(tracked) == 1:
        cid, exp = tracked[0]
        if len(mastered) != exp:
            out.append(Violation(LAYER, "mastery_count",
                                 f"{len(mastered)} mastered weapon(s); class '{cid}' grants {exp}",
                                 exp, len(mastered)))
    elif tracked and len(mastered) > sum(n for _, n in tracked):
        total = sum(n for _, n in tracked)
        out.append(Violation(LAYER, "mastery_count",
                             f"{len(mastered)} mastered weapon(s) exceeds the {total} granted across "
                             f"tracked classes", total, len(mastered), severity=WARNING))
    return out
