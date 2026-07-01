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


_ABILITY_IDS = {"strength": "str", "dexterity": "dex", "constitution": "con",
                "intelligence": "int", "wisdom": "wis", "charisma": "cha"}


def backgrounds(tables):
    """Per background → {abilities: [3 ids], feat?}. Primary source is the master 'Ability Scores and
    Backgrounds' table (inverted — it lists every background under each ability, so it covers all 16);
    the per-background traits tables enrich it with the granted feat where present. Functional facts only."""
    out = {}
    master = next((t for t in tables if (t.get("title") or "").strip() == "Ability Scores and Backgrounds"), None)
    for row in (master or {}).get("rows", []):
        if len(row) < 2:
            continue
        ab = _ABILITY_IDS.get(row[0].strip().lower())
        if not ab:
            continue
        for name in row[1].split(","):
            b = name.strip().lower()
            if b:
                out.setdefault(b, {"abilities": []})["abilities"].append(ab)
    for t in tables:                                  # enrich with the granted feat from traits tables
        rows = t.get("rows", [])
        if not any(len(r) >= 2 and r[0].strip().lower().startswith("ability score") for r in rows):
            continue
        name = re.sub(r"\s*Background Traits$", "", (t.get("title") or "").strip()).strip().lower()
        feat = next((r[1].strip() for r in rows if len(r) >= 2 and r[0].strip().lower().startswith("feat")), None)
        if name in out and feat:
            out[name]["feat"] = re.sub(r"\s*\(see.*?\)", "", feat).strip()
    return {b: v for b, v in out.items() if len(v.get("abilities", [])) == 3}


def spell_lists(tables):
    """Per class → {spell_name: level} from the '<Class> Spells' tables (cantrips = level 0). Names
    only (functional). The union across classes is every spell a 2024 character can legitimately have."""
    out = {}
    for t in tables:
        m = re.match(r"(?:Cantrips \(Level 0 (.+?) Spells\)|Level (\d+) (.+?) Spells)", (t.get("title") or "").strip())
        if not m:
            continue
        cls = (m.group(1) or m.group(3)).strip().lower()
        lvl = 0 if m.group(1) else int(m.group(2))
        cols = t.get("columns", [])
        iS = next((i for i, c in enumerate(cols) if c.strip().lower() == "spell"), 0)
        by_name = out.setdefault(cls, {})
        for r in t.get("rows", []):
            if iS < len(r) and r[iS].strip():
                by_name[r[iS].strip()] = lvl
    return out


def class_hit_dice(tables):
    """Per class → hit die size (int) from 'Core <Class> Traits' → the 'Hit Point Die: D8 …' row."""
    out = {}
    for t in tables:
        m = re.fullmatch(r"Core (.+?) Traits", (t.get("title") or "").strip())
        if not m:
            continue
        for r in t.get("rows", []):
            if len(r) >= 2 and "hit point die" in r[0].strip().lower():
                dm = re.search(r"[dD](\d+)", r[1])
                if dm:
                    out[m.group(1).strip().lower()] = int(dm.group(1))
    return out


def main():
    with open(BOOK) as f:
        tables = _tables(json.load(f))
    os.makedirs(OUT, exist_ok=True)
    prog = class_progression(tables)
    with open(os.path.join(OUT, "class_progression.json"), "w") as f:
        json.dump(prog, f, indent=1)
    print(f"class_progression: {len(prog)} classes -> {OUT}/class_progression.json")

    bg = backgrounds(tables)
    with open(os.path.join(OUT, "backgrounds.json"), "w") as f:
        json.dump(bg, f, indent=1)
    print(f"backgrounds: {len(bg)} -> {OUT}/backgrounds.json")

    lists = spell_lists(tables)
    with open(os.path.join(OUT, "spell_lists.json"), "w") as f:
        json.dump(lists, f, indent=1)
    print(f"spell_lists: {len(lists)} classes, {len({n for d in lists.values() for n in d})} spells "
          f"-> {OUT}/spell_lists.json")

    hd = class_hit_dice(tables)
    with open(os.path.join(OUT, "hit_dice.json"), "w") as f:
        json.dump(hd, f, indent=1)
    print(f"hit_dice: {len(hd)} classes -> {OUT}/hit_dice.json")


if __name__ == "__main__":
    main()
