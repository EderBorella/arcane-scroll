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

    counts = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "records", "*.json"))):
        kind = os.path.splitext(os.path.basename(path))[0]
        recs = json.load(open(path, encoding="utf-8"))
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
    n_cat = 0
    if os.path.exists(cat_path):
        cat = json.load(open(cat_path, encoding="utf-8"))
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
