"""Starting-equipment choices — the model-choice part of equipment, driven by the pre-baked
`class_equipment` relation (built at seed time from the class records; see scripts/seed.py).

Each slot becomes one field. A slot whose alternatives are all concrete (packs, armour, named weapons)
is a plain enum of route labels. A slot where a route is "choose N from a category" is a
*discriminated union*: `{route, weapons}`, where the chosen route fixes exactly how many category
picks it carries — so the grammar enforces the right count and nothing is trimmed afterwards. A direct
"choose from a category" slot is a plain item enum. Multiclass uses the PRIMARY class only."""
from app.generation import helpers as H


def slots(cat, class_idx):
    """Per-slot specs from the class_equipment relation:
      {field, kind:'category'|'enum', enum, n}                 — a plain pick / route enum
      {field, kind:'union', branches:[{label, pick:{enum, n}|None}]}   — route-tagged category picks
    """
    rel = (cat.get("class_equipment") or {}).get(str(class_idx).lower())
    items_by_cat = cat.get("category_items", {})
    out = []
    if not rel:
        return out
    for slot in rel.get("slots", []):
        field, choose = slot["field"], slot.get("choose", 1)
        if "category" in slot:                                      # direct pick from a category
            items = items_by_cat.get(slot["category"])
            if items:
                out.append({"field": field, "kind": "category", "enum": items, "n": choose})
            continue
        alts = slot.get("alternatives", [])
        if not alts:
            continue

        def pick_of(a):
            p = a.get("pick")
            return p if (p and p["category"] in items_by_cat) else None

        if any(pick_of(a) for a in alts):                           # at least one category route → union
            branches = [{"label": a["label"],
                         "pick": {"enum": items_by_cat[pick_of(a)["category"]], "n": pick_of(a)["n"]}
                                 if pick_of(a) else None}
                        for a in alts]
            out.append({"field": field, "kind": "union", "branches": branches})
        else:                                                       # all routes concrete → plain enum
            out.append({"field": field, "kind": "enum", "enum": [a["label"] for a in alts], "n": choose})
    return out


def _primary(classes):
    c0 = classes[0]
    return c0[0] if isinstance(c0, tuple) else (c0["class"] if isinstance(c0, dict) else c0)


def _branch_schema(b):
    """JSON-schema object for one union route: a const route, plus a correctly-sized weapons array
    only when that route is a category pick."""
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"route": {"const": b["label"]}}, "required": ["route"]}
    if b["pick"]:
        schema["properties"]["weapons"] = {"type": "array", "items": {"enum": b["pick"]["enum"]},
                                           "minItems": b["pick"]["n"], "maxItems": b["pick"]["n"]}
        schema["required"] = ["route", "weapons"]
    return schema


def equipment_props(cat, classes):
    """Schema props (+ required names) for the primary class's equipment slots."""
    props, req = {}, []
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        req.append(f)
        if s["kind"] == "union":
            props[f] = {"oneOf": [_branch_schema(b) for b in s["branches"]]}
        else:
            props[f] = {"enum": s["enum"]} if s["n"] == 1 else {
                "type": "array", "items": {"enum": s["enum"]}, "minItems": s["n"], "maxItems": s["n"]}
    return props, req


def _fit(arr, pool, n):
    """Keep on-list picks, pad from the pool. Equipment picks may legitimately repeat (e.g. two of the
    same weapon) — so this does NOT de-dup."""
    keep = [x for x in arr if H._norm(x) in {H._norm(p) for p in pool}]
    while len(keep) < n and pool:
        keep.append(pool[0])
    return keep[:n]


def repair_equipment(cat, ch, classes):
    """Fit each equipment slot to its spec (a grammar can't be fully trusted under truncation, and a
    field may be omitted entirely). Enum slots fit to the pool; union slots get a valid `{route,
    weapons}` with the weapons count the chosen route requires."""
    if not classes:
        return ch
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        if s["kind"] == "union":
            labels = [b["label"] for b in s["branches"]]
            val = ch.get(f)
            route = val.get("route") if isinstance(val, dict) else (val if isinstance(val, str) else None)
            if route not in labels:
                route = labels[0]
            br = next(b for b in s["branches"] if b["label"] == route)
            obj = {"route": route}
            if br["pick"]:
                raw = val.get("weapons") if isinstance(val, dict) else None
                obj["weapons"] = _fit(list(raw or []), br["pick"]["enum"], br["pick"]["n"])
            ch[f] = obj
        else:
            single = s["n"] == 1
            raw = ch.get(f, [])
            cur = [raw] if isinstance(raw, str) else list(raw or [])
            fit = _fit(cur, s["enum"], 1 if single else s["n"])
            if single:
                if fit:
                    ch[f] = fit[0]
            else:
                ch[f] = fit
    return ch
