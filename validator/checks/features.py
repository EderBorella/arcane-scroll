"""Layer: features. Every class feature granted by level is present on the sheet, and choice-count
features (invocations, weapon mastery) carry the right number of picks. Subclass-specific and species
features, and prose/subclass choice-counts (metamagic, maneuvers), are NOT covered here — the
progression data doesn't carry them. Collects all findings; never raises."""
from validator.report import Violation

LAYER = "features"


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def check(sheet, rules):
    out = []
    classes = (sheet.get("identity") or {}).get("classes") or []
    if not classes:
        return out
    features = sheet.get("features") or []
    present = {_norm(f.get("name")) for f in features}
    by_norm = {_norm(f.get("name")): f for f in features}

    # 1) class features present by level
    for c in classes:
        cid, lv = c.get("class"), c.get("level") or 0
        for feat in rules.class_features(cid, lv):
            if _norm(feat) not in present:
                out.append(Violation(LAYER, "feature_missing",
                                     f"{cid} feature '{feat}' (granted by level {lv}) is not on the sheet",
                                     feat, None))

    # 2) choice-count features carry the right number of picks (missing ones are handled above)
    for c in classes:
        cid, lv = c.get("class"), c.get("level") or 0
        for header in (rules.feature_choice_counts.get((cid or "").lower()) or {}):
            expected = rules.feature_choice_expected(cid, header, lv)
            sf = by_norm.get(_norm(header))
            if expected is None or sf is None:
                continue
            n = len(sf.get("choices") or [])
            if n != expected:
                out.append(Violation(LAYER, "feature_choice_count",
                                     f"{cid} feature '{header}' has {n} choice(s); expected {expected} "
                                     f"at level {lv}", expected, n))
    return out
