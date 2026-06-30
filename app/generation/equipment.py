"""Starting-equipment choices — the model-choice part of equipment, driven by the pre-baked
`class_equipment` relation (built at seed time from the class records; see scripts/seed.py).

Each slot becomes one field. A slot whose routes are all concrete (packs, armour, named weapons) is a
plain enum of route labels; a slot with a "choose N from a category" route is a *discriminated union*
`{route, weapons}` so the grammar enforces the exact pick count.

Coherence is engineered into the grammar at build time, not hoped for via the prompt:
  - **Shield rule (always):** a route that grants a shield never offers a two-handed weapon.
  - **Fighting style (when the character has one):** every route — concrete OR category-pick — is
    filtered to the style. Routes whose weapons carry an excluded property (e.g. ranged/two-handed for
    a melee style) are dropped; category picks are filtered to required/excluded properties; route
    weapon-counts are gated by the style's min/max. Every filter falls back to the full options if it
    would empty a slot. Multiclass uses the PRIMARY class only."""
from app.generation import helpers as H


def slots(cat, class_idx):
    """Per-slot specs from the class_equipment relation:
      {field, kind:'category', enum, n}
      {field, kind:'enum'|'union', n, alternatives:[{label, items, pick:{category, enum, n}|None}]}
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
        alts_in = slot.get("alternatives", [])
        if not alts_in:
            continue
        alts = []
        for a in alts_in:
            p = a.get("pick")
            pick = ({"category": p["category"], "enum": items_by_cat[p["category"]], "n": p["n"]}
                    if (p and p["category"] in items_by_cat) else None)
            alts.append({"label": a["label"], "items": a.get("items", []), "pick": pick})
        kind = "union" if any(a["pick"] for a in alts) else "enum"
        out.append({"field": field, "kind": kind, "n": choose, "alternatives": alts})
    return out


# ── coherence: shield rule + fighting-style filtering, applied to the offered routes/weapons ─────────
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


def _shields(cat) -> set:
    return {e["name"] for e in cat.records("equipment").values() if e.get("armor_category") == "Shield"}


def _constrain(alternatives, constraint, wprops, shields):
    """Filter a slot's routes to the fighting style (if any) + the always-on shield rule.
    Concrete routes are dropped when their weapons violate the style's properties; category picks have
    their weapon enum filtered (and two-handed dropped when the route grants a shield); route
    weapon-counts are gated by min/max. Never empties a slot (falls back to the unfiltered options)."""
    constraint = constraint or {}
    maxw, minw = constraint.get("max_weapons"), constraint.get("min_weapons")
    req, exc = set(constraint.get("require_props") or []), set(constraint.get("exclude_props") or [])

    def route_ok(a):
        if a["pick"]:                                               # category pick: count is pick.n
            n = a["pick"]["n"]
            return not ((maxw is not None and n > maxw) or (minw is not None and n < minw))
        weapons = [(it["item"], it.get("qty", 1)) for it in a["items"] if it.get("item") in wprops]
        if not weapons:                                             # non-weapon route (pack/armour/focus)
            return True
        names = [w for w, _ in weapons]
        if any(exc & wprops.get(w, set()) for w in names):
            return False
        if req and not any(req <= wprops.get(w, set()) for w in names):
            return False
        # concrete routes: gate by max only — a two-weapon style gets its second weapon from another
        # slot, so min_weapons must NOT drop a per-slot single-weapon route.
        return not (maxw is not None and sum(q for _, q in weapons) > maxw)

    kept = [a for a in alternatives if route_ok(a)] or alternatives
    out = []
    for a in kept:
        if a["pick"]:
            e = exc | ({"two-handed"} if any(it.get("item") in shields for it in a["items"]) else set())
            if e or req:
                enum = [w for w in a["pick"]["enum"]
                        if (not req or req <= wprops.get(w, set())) and not (e & wprops.get(w, set()))]
                a = {**a, "pick": {**a["pick"], "enum": enum or a["pick"]["enum"]}}
        out.append(a)
    return out


def _primary(classes):
    c0 = classes[0]
    return c0[0] if isinstance(c0, tuple) else (c0["class"] if isinstance(c0, dict) else c0)


def _branch_schema(a):
    """JSON-schema object for one union route: a const route, plus a correctly-sized weapons array
    only when that route is a category pick."""
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"route": {"const": a["label"]}}, "required": ["route"]}
    if a["pick"]:
        schema["properties"]["weapons"] = {"type": "array", "items": {"enum": a["pick"]["enum"]},
                                           "minItems": a["pick"]["n"], "maxItems": a["pick"]["n"]}
        schema["required"] = ["route", "weapons"]
    return schema


def equipment_props(cat, classes, fighting_style=None):
    """Schema props (+ required names) for the primary class's equipment slots, coherence-constrained
    (shield rule always; fighting style when the character has one)."""
    constraint = (cat.get("fighting_style_equipment") or {}).get(fighting_style or "") or {}
    wprops, shields = _weapon_props(cat), _shields(cat)
    props, req = {}, []
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        req.append(f)
        if s["kind"] == "category":
            props[f] = {"enum": s["enum"]} if s["n"] == 1 else {
                "type": "array", "items": {"enum": s["enum"]}, "minItems": s["n"], "maxItems": s["n"]}
            continue
        alts = _constrain(s["alternatives"], constraint, wprops, shields)
        if s["kind"] == "union":
            props[f] = {"oneOf": [_branch_schema(a) for a in alts]}
        else:
            labels = [a["label"] for a in alts]
            props[f] = {"enum": labels} if s["n"] == 1 else {
                "type": "array", "items": {"enum": labels}, "minItems": s["n"], "maxItems": s["n"]}
    return props, req


def _fit(arr, pool, n):
    """Keep on-list picks, pad from the pool. Equipment picks may legitimately repeat (e.g. two of the
    same weapon) — so this does NOT de-dup."""
    keep = [x for x in arr if H._norm(x) in {H._norm(p) for p in pool}]
    while len(keep) < n and pool:
        keep.append(pool[0])
    return keep[:n]


def repair_equipment(cat, ch, classes):
    """Fit each equipment slot to its spec, validated against the FULL options (the coherence-narrowed
    grammar only ever yields a subset, so repair never fights it). Enum/category slots fit to the pool;
    union slots get a valid `{route, weapons}` with the weapons count the chosen route requires."""
    if not classes:
        return ch
    for s in slots(cat, _primary(classes)):
        f = s["field"]
        if s["kind"] == "union":
            labels = [a["label"] for a in s["alternatives"]]
            val = ch.get(f)
            route = val.get("route") if isinstance(val, dict) else (val if isinstance(val, str) else None)
            if route not in labels:
                route = labels[0]
            alt = next(a for a in s["alternatives"] if a["label"] == route)
            obj = {"route": route}
            if alt["pick"]:
                raw = val.get("weapons") if isinstance(val, dict) else None
                obj["weapons"] = _fit(list(raw or []), alt["pick"]["enum"], alt["pick"]["n"])
            ch[f] = obj
        else:
            pool = s["enum"] if s["kind"] == "category" else [a["label"] for a in s["alternatives"]]
            single = s["n"] == 1
            raw = ch.get(f, [])
            cur = [raw] if isinstance(raw, str) else list(raw or [])
            fit = _fit(cur, pool, 1 if single else s["n"])
            if single:
                if fit:
                    ch[f] = fit[0]
            else:
                ch[f] = fit
    return ch
