"""Mine the 2024 rules data — functional facts ONLY (names, levels, numbers, mechanics; never prose) —
from the source rulebook JSON into the validator's data dir. Generic: classes are discovered from
table titles, so no game content is hard-coded here. Prose (`text`) is never read into the output.

  BOOK_JSON       source rulebook extraction (default: resources/book.json)
  VALIDATOR_DATA  output data dir           (default: arcane-validator-data)
"""
import json
import os
import re

BOOK = os.environ.get("BOOK_JSON", "/data/projects/resources/book.json")
OUT = os.environ.get("VALIDATOR_DATA", "/data/projects/arcane-validator-data")


def _tables(book):
    return [t for s in book.get("sections", []) for t in (s.get("tables") or [])]


def _col(cols, name):
    for i, c in enumerate(cols):
        if c.strip().lower() == name.lower():
            return i
    return None


def _int(s):
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else None


def class_progression(tables):
    """Per class → {level: {proficiency_bonus, cantrips_known?, prepared_spells?, features[]}} from the
    '<Class> Features' tables. Feature *names* only (functional); no descriptions."""
    out = {}
    for t in tables:
        m = re.fullmatch(r"(.+?) Features", (t.get("title") or "").strip())
        if not m:
            continue
        cols = t.get("columns", [])
        iL = _col(cols, "Level")
        if iL is None:
            continue
        iPB, iC, iP, iF = (_col(cols, "Proficiency Bonus"), _col(cols, "Cantrips"),
                           _col(cols, "Prepared Spells"), _col(cols, "Class Features"))
        levels = {}
        for r in t.get("rows", []):
            lvl = _int(r[iL]) if iL < len(r) else None
            if lvl is None:
                continue
            e = {}
            if iPB is not None and iPB < len(r):
                e["proficiency_bonus"] = _int(r[iPB])
            if iC is not None and iC < len(r) and _int(r[iC]) is not None:
                e["cantrips_known"] = _int(r[iC])
            if iP is not None and iP < len(r) and _int(r[iP]) is not None:
                e["prepared_spells"] = _int(r[iP])
            if iF is not None and iF < len(r):
                e["features"] = [f.strip() for f in re.split(r"[,;]", r[iF]) if f.strip()]
            levels[str(lvl)] = e
        if levels:
            out[m.group(1).strip().lower()] = levels
    return out


def main():
    with open(BOOK) as f:
        tables = _tables(json.load(f))
    os.makedirs(OUT, exist_ok=True)
    prog = class_progression(tables)
    with open(os.path.join(OUT, "class_progression.json"), "w") as f:
        json.dump(prog, f, indent=1)
    print(f"class_progression: {len(prog)} classes -> {OUT}/class_progression.json")


if __name__ == "__main__":
    main()
