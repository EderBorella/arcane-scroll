"""Starting-equipment choices — the model-choice part of equipment, driven by the pre-baked
`class_equipment` relation (built at seed time from the class records; see scripts/seed.py).

Each slot becomes one field. A slot whose alternatives are all concrete (packs, armour, named weapons)
is a plain enum of route labels. A slot where a route is "choose N from a category" is a
*discriminated union*: `{route, weapons}`, where the chosen route fixes exactly how many category
picks it carries — so the grammar enforces the right count and nothing is trimmed afterwards.

When the character has a **fighting style**, the union is further constrained to that style at
grammar-build time (engineered coherence, not a prompt hope): a one-weapon style only offers the
weapon-and-shield route, a two-weapon style only the two-weapon route, and the weapon enum is filtered
by property (no two-handed for a duelist, ranged-only for an archer, two-handed-only for a great-weapon
style). Filters fall back to the full options if they would empty a slot. Multiclass uses the PRIMARY
class only."""
from app.generation import helpers as H


def slots(cat, class_idx):
    """Per-slot specs from the class_equipment relation:
      {field, kind:'category'|'enum', enum, n}
      {field, kind:'union', branches:[{label, pick:{category, enum, n}|None}]}
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
            branches = []
            for a in alts:
                p = pick_of(a)
                branches.append({"label": a["label"],
                                 "pick": {"category": p["category"], "enum": items_by_cat[p["category"]],
                                          "n": p["n"]} if p else None})
            out.append({"field": field, "kind": "union", "branches": branches})
        else:                                                       # all routes concrete → plain enum
            out.append({"field": field, "kind": "enum", "enum": [a["label"] for a in alts], "n": choose})
    return out


# ── fighting-style coherence (constrain the weapon union to the style, before the model call) ────────
def _weapon_props(cat) -> dict:
    """Weapon name -> set of property tags (a 'ranged' tag is added for ranged/ammunition weapons)."""
    out = {}
    for e in cat.records("equipment").values():
        if e.get("equipment_category", {}).get("index") != "weapon":
            continue
        props = {str(p.get("index") or p.get("name", "")).lower() for p in (e.get("properties") or [])}
        if e.get("weapon_range") == "Ranged" or "ammunition" in props:
            props.add("ranged")
        out[e["name"]] = props
    return out


def _filter_branches(branches, constraint, wprops):
    """Apply a fighting style's constraint to a union slot's branches: keep only routes whose weapon
    count fits (max/min_weapons), and filter each route's weapon enum by property. Every filter falls
    back to the unfiltered value if it would empty the result — coherence must never break generation."""
    if not constraint or not any(b["pick"] and "weapon" in b["pick"]["category"] for b in branches):
        return branches
    maxw, minw = constraint.get("max_weapons"), constraint.get("min_weapons")
    req, exc = set(constraint.get("require_props") or []), set(constraint.get("exclude_props") or [])

    def fits(b):
        n = b["pick"]["n"] if b["pick"] else 0
        return not ((maxw is not None and n > maxw) or (minw is not None and n < minw))

    kept = [b for b in branches if fits(b)] or branches
    if req or exc:
        out = []
        for b in kept:
            if b["pick"] and "weapon" in b["pick"]["category"]:
                enum = [w for w in b["pick"]["enum"]
                        if (not req or req <= wprops.get(w, set())) and not (exc & wprops.get(w, set()))]
                b = {**b, "pick": {**b["pick"], "enum": enum or b["pick"]["enum"]}}
            out.append(b)
        kept = out
    return kept


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


def equipment_props(cat, classes, fighting_style=None):
    """Schema props (+ required names) for the primary class's equipment slots, constrained to the
    character's fighting style when it has one."""
    constraint = (cat.get("fighting_style_equipment") or {}).get(fighting_style or "") or {}
    wprops = _weapon_props(cat) if constraint else {}
    props, req = {}, []
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        req.append(f)
        if s["kind"] == "union":
            branches = _filter_branches(s["branches"], constraint, wprops)
            props[f] = {"oneOf": [_branch_schema(b) for b in branches]}
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
    weapons}` with the weapons count the chosen route requires. Validated against the FULL options (the
    style-narrowed grammar only ever yields a subset, so this never fights the style)."""
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
