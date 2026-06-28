"""Feature-choice descriptors — the "expanded contract" the model fills on top of the base sheet.

Each descriptor is `{field, enum, n}`, gated by `(class, subclass, level)`. Pure + catalog-driven:
the value lists come from the catalog by neutral key; the gating mechanics live in code. The sheet
generator merges these into the per-request grammar and fits them in repair.

This increment covers **fighting style** and **expertise**. Subclass feature oddities, feats/ASI,
and equipment extend this same module in follow-ups."""
from app.generation import helpers as H


def _expertise_count(ci: str, lv: int) -> int:
    """How many proficient skills a class doubles (Rogue: 2 @L1 +2 @L6; Bard: 2 @L3 +2 @L10)."""
    if ci == "rogue":
        return (2 if lv >= 1 else 0) + (2 if lv >= 6 else 0)
    if ci == "bard":
        return (2 if lv >= 3 else 0) + (2 if lv >= 10 else 0)
    return 0


def _fighting_style_classes(cat, classes):
    """Classes (from the request) whose level grants a fighting style."""
    levels, styles = cat.get("fighting_style_level", {}), cat.get("fighting_styles", {})
    return [ci for ci, lv, _ in classes if ci in styles and lv >= levels.get(ci, 99)]


def descriptors(cat, classes):
    """classes: [(ci, lv, subclass)]. Ordered [{field, enum, n}] for the feature choices granted."""
    out = []
    granting = _fighting_style_classes(cat, classes)
    if granting:
        styles = cat.get("fighting_styles", {})
        opts = sorted(set().union(*[set(styles[ci]) for ci in granting]))
        out.append({"field": "fighting_style", "enum": opts, "n": len(granting)})

    exp_total = sum(_expertise_count(ci, lv) for ci, lv, _ in classes)
    if exp_total:
        _, skill_idx = H.class_skill_grant(cat, classes[0][0])
        skills = H.skill_names(cat, skill_idx)          # repair narrows these to the chosen skills
        n = min(exp_total, len(skills))
        if n:
            out.append({"field": "expertise", "enum": skills, "n": n})
    return out


def feature_props(cat, classes):
    """Schema props (+ required names) for the feature-choice fields."""
    props, req = {}, []
    for d in descriptors(cat, classes):
        props[d["field"]] = {"type": "array", "items": {"enum": d["enum"]},
                             "minItems": d["n"], "maxItems": d["n"], "uniqueItems": True}
        req.append(d["field"])
    return props, req


def repair_features(cat, ch, classes):
    """Fit each feature field to its enum/count. Expertise must double *chosen* skills, so it's fit
    against `skill_choices` rather than the whole class list."""
    for d in descriptors(cat, classes):
        if d["field"] not in ch:
            continue
        pool = ch.get("skill_choices", []) if d["field"] == "expertise" else d["enum"]
        ch[d["field"]] = H._dedup_pad(ch[d["field"]], pool, d["n"])
    return ch
