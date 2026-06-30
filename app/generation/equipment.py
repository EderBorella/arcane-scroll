"""Starting-equipment choices — the model-choice part of equipment, driven by the pre-baked
`class_equipment` relation (built at seed time from the class records; see scripts/seed.py). Each
class equipment slot becomes a *route* enum — the (a)/(b) alternative labels the model picks — plus a
*companion* enum of concrete items when an alternative is "choose N from a category". Multiclass uses
the PRIMARY class only: a second class grants no starting equipment. Pure + catalog-driven — the slot
structure comes from the relation, the category item lists from the catalog by neutral key."""
from app.generation import helpers as H


def slots(cat, class_idx):
    """[{field, enum, n, companion}] for one class, from the class_equipment relation;
    companion = {field, enum, n} or None."""
    rel = (cat.get("class_equipment") or {}).get(str(class_idx).lower())
    items_by_cat = cat.get("category_items", {})
    out = []
    if not rel:
        return out
    for slot in rel.get("slots", []):
        field, choose = slot["field"], slot.get("choose", 1)
        if "category" in slot:                              # direct pick from a category
            items = items_by_cat.get(slot["category"])
            if items:
                out.append({"field": field, "enum": items, "n": choose, "companion": None})
            continue
        alts = slot.get("alternatives", [])
        labels = [a["label"] for a in alts]
        picks = [a["pick"] for a in alts if a.get("pick") and a["pick"]["category"] in items_by_cat]
        companion = None
        if picks:
            cat_idx = max(picks, key=lambda p: p["n"])["category"]
            n = max(p["n"] for p in picks if p["category"] == cat_idx)
            companion = {"field": f"{field}_pick", "enum": items_by_cat[cat_idx], "n": n}
        if labels:
            out.append({"field": field, "enum": labels, "n": choose, "companion": companion})
    return out


def _primary(classes):
    c0 = classes[0]
    return c0[0] if isinstance(c0, tuple) else (c0["class"] if isinstance(c0, dict) else c0)


def equipment_props(cat, classes):
    """Schema props (+ required names) for the primary class's equipment slots and companions."""
    props, req = {}, []
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        props[f] = {"enum": s["enum"]} if s["n"] == 1 else {
            "type": "array", "items": {"enum": s["enum"]}, "minItems": s["n"], "maxItems": s["n"]}
        req.append(f)
        if s["companion"]:
            cp = s["companion"]
            props[cp["field"]] = {"type": "array", "items": {"enum": cp["enum"]},
                                  "minItems": cp["n"], "maxItems": cp["n"]}
            req.append(cp["field"])
    return props, req


def _fit(arr, pool, n):
    """Keep on-list picks, pad from the pool. Unlike feature choices, equipment companions may
    legitimately repeat (e.g. two of the same weapon) — so this does NOT de-dup."""
    keep = [x for x in arr if H._norm(x) in {H._norm(p) for p in pool}]
    while len(keep) < n and pool:
        keep.append(pool[0])
    return keep[:n]


def repair_equipment(cat, ch, classes):
    """Fit each equipment route + companion to its enum/count (a grammar can't enforce count)."""
    if not classes:
        return ch
    for s in slots(cat, _primary(classes)):
        for spec, is_route in ((s, True), (s["companion"], False)):
            if not spec:
                continue
            f = spec["field"]
            single = is_route and s["n"] == 1
            # synthesize an omitted field by padding from the slot's enum, rather than skipping it
            raw = ch.get(f, [])
            cur = [raw] if isinstance(raw, str) else list(raw or [])
            fit = _fit(cur, spec["enum"], 1 if single else spec["n"])
            if single:
                if fit:
                    ch[f] = fit[0]
            else:
                ch[f] = fit
    return ch
