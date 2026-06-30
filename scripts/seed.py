#!/usr/bin/env python3
"""Build the SQLite catalog from the local reference data. Data-free: contains no content, only
load logic — paths come from the environment (Docker fills them):

  ARCANE_DATA_DIR   source data dir — every *.json under  <dir>/records/  becomes rows in `entries`
                    (the kind = the file's stem), and  <dir>/catalog.json  fills the `catalog` table.
  ARCANE_DB_PATH    output SQLite file (recreated each run)

Run:  ARCANE_DATA_DIR=/path/to/data ARCANE_DB_PATH=/path/to/catalog.db python seed.py

Schema:
  entries(kind, idx, name, data)   one row per source record; data = original JSON object.
  catalog(name, data)              key -> JSON value for the supplemental tables/lists.
The service loads both into memory at startup.
"""
import glob, json, os, sqlite3, sys


def _idx(rec):
    return rec.get("index") or rec.get("url") or json.dumps(rec, sort_keys=True)[:80]


# ── derived: the class -> starting-equipment relation (consumed by generation + derivation) ──────────
# Normalises each class's raw starting_equipment / starting_equipment_options into a flat relation so
# neither the grammar builder nor inventory assembly has to walk the nested option JSON, and the
# model's chosen route label maps 1:1 back to its concrete items. Pure structure transform — no content.
def _item_qty(o):
    return {"item": o.get("of", {}).get("name"), "qty": o.get("count", 1)}


def _parse_alt(a):
    """One (a)/(b) alternative -> {label, items:[{item,qty}], pick:{category,n}|None}."""
    t = a.get("option_type")
    if t == "counted_reference":
        iq = _item_qty(a)
        return {"label": iq["item"] if iq["qty"] == 1 else f"{iq['qty']} {iq['item']}",
                "items": [iq], "pick": None}
    if t == "choice":
        ch = a["choice"]
        cat = ch.get("from", {}).get("equipment_category", {}).get("index")
        return {"label": ch.get("desc") or f"{ch.get('choose')} {cat or 'item'}",
                "items": [], "pick": {"category": cat, "n": ch.get("choose", 1)} if cat else None}
    if t == "multiple":
        items, pick, labels = [], None, []
        for x in a.get("items", []):
            sub = _parse_alt(x)
            items += sub["items"]
            pick = pick or sub["pick"]
            labels.append(sub["label"])
        return {"label": " + ".join(labels), "items": items, "pick": pick}
    return {"label": "?", "items": [], "pick": None}


def build_class_equipment(class_records) -> dict:
    """{class_index: {fixed:[{item,qty}], slots:[direct-category | alternatives]}} for every class."""
    out = {}
    for c in class_records:
        ci = c.get("index")
        fixed = [{"item": e.get("equipment", {}).get("name"), "qty": e.get("quantity", 1)}
                 for e in c.get("starting_equipment", [])]
        slots = []
        for i, slot in enumerate(c.get("starting_equipment_options", [])):
            frm, field = slot.get("from", {}), f"equipment_{i}"
            if frm.get("option_set_type") == "equipment_category":
                slots.append({"field": field, "choose": slot.get("choose", 1),
                              "category": frm.get("equipment_category", {}).get("index")})
            else:
                slots.append({"field": field, "choose": slot.get("choose", 1),
                              "alternatives": [_parse_alt(a) for a in frm.get("options", [])]})
        out[ci] = {"fixed": fixed, "slots": slots}
    return out


def main():
    data_dir = os.environ.get("ARCANE_DATA_DIR")
    db_path = os.environ.get("ARCANE_DB_PATH")
    if not data_dir or not db_path:
        sys.exit("ERROR: set ARCANE_DATA_DIR and ARCANE_DB_PATH")

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("CREATE TABLE entries (kind TEXT, idx TEXT, name TEXT, data TEXT, PRIMARY KEY(kind, idx))")
    cur.execute("CREATE TABLE catalog (name TEXT PRIMARY KEY, data TEXT)")

    counts, class_records = {}, []
    for path in sorted(glob.glob(os.path.join(data_dir, "records", "*.json"))):
        kind = os.path.splitext(os.path.basename(path))[0]
        recs = json.load(open(path, encoding="utf-8"))
        if kind == "classes":
            class_records = recs
        seen, rows = set(), []
        for r in recs:
            i = _idx(r)
            while i in seen:
                i += "_"
            seen.add(i)
            rows.append((kind, i, r.get("name") or i, json.dumps(r, ensure_ascii=False)))
        cur.executemany("INSERT INTO entries VALUES (?,?,?,?)", rows)
        counts[kind] = len(rows)

    cat_path = os.path.join(data_dir, "catalog.json")
    cat = json.load(open(cat_path, encoding="utf-8")) if os.path.exists(cat_path) else {}
    # derive the class->equipment relation from the class records (unless hand-supplied in catalog.json)
    cat.setdefault("class_equipment", build_class_equipment(class_records))
    cur.executemany("INSERT INTO catalog VALUES (?,?)",
                    [(k, json.dumps(v, ensure_ascii=False)) for k, v in cat.items()])
    n_cat = len(cat)

    con.commit()
    con.close()
    print(f"seeded {db_path}")
    print(f"  entries: {counts} = total {sum(counts.values())} rows")
    print(f"  catalog: {n_cat} entries")


if __name__ == "__main__":
    main()
