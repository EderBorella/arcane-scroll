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

    if tracked:
        # Ruling: multiclass Weapon Mastery does NOT stack — the character masters the HIGHEST single
        # class's count (max among the mastery-granting classes), not the sum. Fewer than that has no
        # legal source (ERROR); more can come from a feat/subclass (advisory WARNING).
        exp = max(n for _, n in tracked)
        if len(mastered) < exp:
            out.append(Violation(LAYER, "mastery_count",
                                 f"{len(mastered)} mastered weapon(s); expected {exp} "
                                 f"(highest among the character's mastery-granting classes)",
                                 exp, len(mastered)))
        elif len(mastered) > exp:
            out.append(Violation(LAYER, "mastery_count",
                                 f"{len(mastered)} mastered weapon(s) exceeds {exp} (highest single class); "
                                 f"extra masteries may come from a feat or subclass",
                                 exp, len(mastered), severity=WARNING))
    return out
