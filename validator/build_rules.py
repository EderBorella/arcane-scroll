"""Build the validator's rules data files from the reference source.

Reads the structured reference JSON and writes the lookup tables the validator checks against —
class progression, backgrounds, spell lists, hit dice, class proficiencies — into the data dir.
Output is purely structural/numeric (identifiers, levels, counts) and is regenerated whenever the
reference is updated.

  SOURCE_JSON     reference data file  (default: resources/book.json)
  VALIDATOR_DATA  output data dir      (default: arcane-validator-data)
"""
import json
import os
import re

SOURCE = os.environ.get("SOURCE_JSON", "/data/projects/resources/book.json")
OUT = os.environ.get("VALIDATOR_DATA", "/data/projects/arcane-validator-data")

_ABILITY_IDS = {"strength": "str", "dexterity": "dex", "constitution": "con",
                "intelligence": "int", "wisdom": "wis", "charisma": "cha"}


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
    '<Class> Features' tables."""
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


def _trait_pairs(section):
    """Label→value trait pairs for a background block, from its table rows and section text."""
    pairs = {}
    for t in (section.get("tables") or []):
        for r in t.get("rows", []):
            if len(r) >= 2 and r[0].strip().endswith(":"):
                pairs.setdefault(r[0].strip().rstrip(":").strip().lower(), r[1].strip())
    for line in (section.get("text") or "").splitlines():
        m = re.match(r"\s*(Ability Scores|Feat|Skill Proficiencies|Tool Proficiency)\s*:\s*(.+)", line)
        if m:
            pairs.setdefault(m.group(1).lower(), m.group(2).strip())
    return pairs


def backgrounds(sections):
    """Per background → {abilities: [3 ids], skills: [names], feat?}. Abilities come from the master
    'Ability Scores and Backgrounds' table (covers all 16); skills/feat come from each background's
    trait block (table or section text)."""
    tables = [t for s in sections for t in (s.get("tables") or [])]
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
    out = {b: v for b, v in out.items() if len(v["abilities"]) == 3}
    names = set(out)
    for s in sections:
        pairs = _trait_pairs(s)
        if "skill proficiencies" not in pairs:
            continue
        cand = re.sub(r"\s*Background Traits$", "", (s.get("section") or "").strip()).strip().lower()
        if cand not in names:
            for t in (s.get("tables") or []):
                c2 = re.sub(r"\s*Background Traits$", "", (t.get("title") or "").strip()).strip().lower()
                if c2 in names:
                    cand = c2
                    break
        if cand not in names:
            continue
        out[cand].setdefault("skills", [x.strip() for x in re.split(r",|\band\b", pairs["skill proficiencies"]) if x.strip()])
        feat = pairs.get("feat")
        if feat:
            out[cand].setdefault("feat", re.sub(r"\s*\(see.*?\)", "", feat).strip())
    return out


def spell_lists(tables):
    """Per class → {spell_name: level} from the '<Class> Spells' tables (cantrips = level 0). The union
    across classes is the set of valid spell names."""
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
    """Per class → hit die size (int) from 'Core <Class> Traits' → the 'Hit Point Die' row."""
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


def class_proficiencies(tables):
    """Per class → {saving_throws: [ability ids], skills: {choose: N, from: [names] | None}} from the
    'Core <Class> Traits' saving-throw + skill rows ('from' is None when the class picks any skills)."""
    out = {}
    for t in tables:
        m = re.fullmatch(r"Core (.+?) Traits", (t.get("title") or "").strip())
        if not m:
            continue
        entry = {}
        for r in t.get("rows", []):
            if len(r) < 2:
                continue
            k = r[0].strip().lower()
            if "saving throw" in k:
                saves = [_ABILITY_IDS[a.strip().lower()] for a in re.split(r"\band\b|,", r[1])
                         if a.strip().lower() in _ABILITY_IDS]
                if saves:
                    entry["saving_throws"] = saves
            elif k.startswith("skill prof"):
                s = r[1]
                cm = re.search(r"choose (?:any )?(\d+)", s, re.I)
                if "any" in s.lower():
                    frm = None
                else:
                    after = s.split(":", 1)[1] if ":" in s else ""
                    frm = [x.strip() for x in re.split(r",|\bor\b", after) if x.strip()]
                entry["skills"] = {"choose": int(cm.group(1)) if cm else None, "from": frm}
        if entry:
            out[m.group(1).strip().lower()] = entry
    return out


def main():
    with open(SOURCE) as f:
        book = json.load(f)
    tables = _tables(book)
    os.makedirs(OUT, exist_ok=True)

    prog = class_progression(tables)
    with open(os.path.join(OUT, "class_progression.json"), "w") as f:
        json.dump(prog, f, indent=1)
    print(f"class_progression: {len(prog)} classes -> {OUT}/class_progression.json")

    bg = backgrounds(book["sections"])
    with open(os.path.join(OUT, "backgrounds.json"), "w") as f:
        json.dump(bg, f, indent=1)
    missing_skills = [b for b, v in bg.items() if not v.get("skills")]
    print(f"backgrounds: {len(bg)} -> {OUT}/backgrounds.json"
          + (f"  [!] no skills for: {missing_skills}" if missing_skills else "  (all have skills)"))

    lists = spell_lists(tables)
    with open(os.path.join(OUT, "spell_lists.json"), "w") as f:
        json.dump(lists, f, indent=1)
    print(f"spell_lists: {len(lists)} classes, {len({n for d in lists.values() for n in d})} spells "
          f"-> {OUT}/spell_lists.json")

    hd = class_hit_dice(tables)
    with open(os.path.join(OUT, "hit_dice.json"), "w") as f:
        json.dump(hd, f, indent=1)
    print(f"hit_dice: {len(hd)} classes -> {OUT}/hit_dice.json")

    prof = class_proficiencies(tables)
    with open(os.path.join(OUT, "class_proficiencies.json"), "w") as f:
        json.dump(prof, f, indent=1)
    print(f"class_proficiencies: {len(prof)} classes -> {OUT}/class_proficiencies.json")


if __name__ == "__main__":
    main()
