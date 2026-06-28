"""Starting-equipment choices — the model-choice part of equipment. (Fixed class/background packages
are derivation work, added later.) Each class equipment slot becomes a *route* enum — the (a)/(b)
alternatives the model picks — plus a *companion* enum of concrete items when an alternative is
"choose N from a category". Multiclass uses the PRIMARY class only: a second class grants no starting
equipment. Pure + catalog-driven — the slot structure comes from the class record, the category item
lists from the catalog by neutral key."""
from app.generation import helpers as H


def _item_label(o):
    count, name = o.get("count", 1), o.get("of", {}).get("name", "?")
    return name if count == 1 else f"{count} {name}"


def _alt_label(a):
    """A human label for one (a)/(b) alternative the model chooses between."""
    t = a.get("option_type")
    if t == "counted_reference":
        return _item_label(a)
    if t == "choice":
        ch = a["choice"]
        return ch.get("desc") or f"{ch.get('choose')} {ch.get('from', {}).get('equipment_category', {}).get('index', 'item')}"
    if t == "multiple":
        return " + ".join(_item_label(x) if x.get("option_type") == "counted_reference"
                          else (x.get("choice", {}).get("desc") or "a weapon") for x in a.get("items", []))
    return "?"


def _cat_pick(a):
    """(category_index, choose) if the alternative includes a category sub-choice, else None."""
    if a.get("option_type") == "choice":
        ch = a["choice"]
        return ch.get("from", {}).get("equipment_category", {}).get("index"), ch.get("choose", 1)
    if a.get("option_type") == "multiple":
        for x in a.get("items", []):
            if x.get("option_type") == "choice":
                ch = x["choice"]
                return ch.get("from", {}).get("equipment_category", {}).get("index"), ch.get("choose", 1)
    return None


def slots(cat, class_idx):
    """[{field, enum, n, companion}] for one class; companion = {field, enum, n} or None."""
    c = cat.record("classes", str(class_idx).lower())
    items_by_cat = cat.get("category_items", {})
    out = []
    if not c:
        return out
    for i, slot in enumerate(c.get("starting_equipment_options", [])):
        frm, choose, field = slot.get("from", {}), slot.get("choose", 1), f"equipment_{i}"
        if frm.get("option_set_type") == "equipment_category":          # direct pick from a category
            items = items_by_cat.get(frm.get("equipment_category", {}).get("index"))
            if items:
                out.append({"field": field, "enum": items, "n": choose, "companion": None})
            continue
        alts = frm.get("options", [])
        labels = [_alt_label(a) for a in alts]
        cps = [p for p in (_cat_pick(a) for a in alts) if p and p[0] in items_by_cat]
        companion = None
        if cps:
            cat_idx = max(cps, key=lambda x: x[1])[0]
            companion = {"field": f"{field}_pick", "enum": items_by_cat[cat_idx],
                         "n": max(n for idx, n in cps if idx == cat_idx)}
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
            if not spec or spec["field"] not in ch:
                continue
            f = spec["field"]
            single = is_route and s["n"] == 1
            cur = [ch[f]] if isinstance(ch[f], str) else list(ch[f])
            fit = _fit(cur, spec["enum"], 1 if single else spec["n"])
            ch[f] = fit[0] if single else fit
    return ch
