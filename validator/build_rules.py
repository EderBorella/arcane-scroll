"""Build the validator's rules data files from the reference source.

Reads the structured reference JSON and writes the lookup tables the validator checks against —
class progression, backgrounds, spell lists, hit dice, class proficiencies — into the data dir.
Output is purely structural/numeric (identifiers, levels, counts) and is regenerated whenever the
reference is updated.

Both paths come from the environment (see .env.example) — nothing is hardcoded:
  SOURCE_JSON               path to the reference source JSON
  VALIDATOR_DATA_DIR_HOST   output data dir (where the validator loads its rules from)
"""
import json
import os
import re

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
                e["features"] = [f.strip() for f in re.split(r"[,;]", r[iF])
                                 if f.strip() and f.strip() != "—"]     # '—' = no new feature that level
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
    """Per class → {spell_name: level} from the '<Class> Spells' tables (cantrips = level 0). Also
    catches '<Class> Cantrips (continued)' tables (level 0). The union across classes is the set of
    valid spell names. Only classes with at least one spell row get an entry (no empty keys)."""
    out = {}
    for t in tables:
        title = (t.get("title") or "").strip()
        m = re.match(r"(?:Cantrips \(Level 0 (.+?) Spells\)|(.+?) Cantrips(?: \(continued\))?$|Level (\d+) (.+?) Spells)", title)
        if not m:
            continue
        cantrip_cls = m.group(1) or m.group(2)
        cls = (cantrip_cls or m.group(4)).strip().lower()
        lvl = 0 if cantrip_cls else int(m.group(3))
        cols = t.get("columns", [])
        iS = next((i for i, c in enumerate(cols) if c.strip().lower() == "spell"), 0)
        for r in t.get("rows", []):
            if iS < len(r) and r[iS].strip():
                out.setdefault(cls, {})[r[iS].strip()] = lvl
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


_ARMOR_TOKENS = ("light", "medium", "heavy", "shield")
_WEAPON_TOKENS = ("simple", "martial")


def _category_tokens(text, vocab):
    """The closed-vocabulary category tokens present in a proficiency phrase (e.g. 'Simple and Martial
    weapons' → ['simple', 'martial']). 'shield' normalises to 'shields'. Empty for 'None'."""
    low = (text or "").lower()
    if low.strip() in ("none", "", "—"):
        return []
    return [("shields" if tok == "shield" else tok) for tok in vocab if tok in low]


def _tool_grants(text):
    """A class's tool grant: {fixed: [names]} for concrete grants, or {choose: N} for a player choice
    ('Choose 3 Musical Instruments'). Fixed grants can be checked for presence; choices cannot."""
    s = (text or "").strip()
    if not s or s.lower() == "none":
        return None
    cm = re.match(r"choose (?:any )?(\w+)", s, re.I)
    if cm:
        return {"choose": {"one": 1, "two": 2, "three": 3}.get(cm.group(1).lower(), _int(cm.group(1)))}
    return {"fixed": [x.strip() for x in re.split(r",|\band\b", s) if x.strip()]}


def class_proficiencies(tables):
    """Per class → {saving_throws, skills{choose,from}, armor[], weapons[], tools{fixed|choose}} from the
    'Core <Class> Traits' rows. Armour/weapon are closed-vocabulary category tokens; 'from'/tools are
    None/absent when the class grants nothing checkable."""
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
            if "primary ability" in k:
                prim = [_ABILITY_IDS[a.strip().lower()] for a in re.split(r"\bor\b|,|\band\b", r[1])
                        if a.strip().lower() in _ABILITY_IDS]
                if prim:
                    entry["primary"] = prim       # >1 ⇒ any-of (e.g. "Strength or Dexterity")
            elif "saving throw" in k:
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
            elif "armor training" in k or k.startswith("armor prof"):
                entry["armor"] = _category_tokens(r[1], _ARMOR_TOKENS)
            elif "weapon prof" in k:
                toks = _category_tokens(r[1], _WEAPON_TOKENS)
                # A conditional martial grant ("Martial weapons that have the Finesse or Light
                # property") is NOT full martial proficiency; assert only the unconditional categories.
                if "martial" in toks and re.search(r"martial weapons that have|property", r[1], re.I):
                    toks = [t for t in toks if t != "martial"]
                entry["weapons"] = toks
            elif "tool prof" in k:
                tools = _tool_grants(r[1])
                if tools:
                    entry["tools"] = tools
        if entry:
            out[m.group(1).strip().lower()] = entry
    return out


def _caster_classes(prog):
    """Class ids that cast — they carry a prepared-spell or cantrip count in the progression."""
    return {c for c, levels in prog.items()
            if any(("prepared_spells" in e or "cantrips_known" in e) for e in levels.values())}


def _slot_cols(cols):
    """Column index → spell level, for the slot columns (header is, or ends in, a digit 1-9)."""
    out = {}
    for i, c in enumerate(cols):
        s = c.strip()
        if s.lower().endswith("level"):     # the row's own character-level column
            continue
        m = re.search(r"([1-9])$", s)
        if m:
            out[i] = int(m.group(1))
    return out


def _slot_table(t):
    """A '<Class> Features' / '<X> Spellcasting' table → {char_level: {spell_level: n}} (nonzero only)."""
    cols = t.get("columns", [])
    sc = _slot_cols(cols)
    if not sc:
        return None
    iL = next((i for i, c in enumerate(cols) if c.strip().lower().endswith("level")), 0)
    table = {}
    for r in t.get("rows", []):
        lvl = _int(r[iL]) if iL < len(r) else None
        if lvl is None:
            continue
        row = {}
        for idx, splvl in sc.items():
            if idx < len(r) and _int(r[idx]):
                row[str(splvl)] = _int(r[idx])
        table[str(lvl)] = row
    return table


def spell_slots(tables, prog):
    """Slot data: each caster class's own table, the multiclass table, pact magic, third-caster
    subclass tables, and each class's caster type (full/half/pact). Non-casters are omitted."""
    casters = _caster_classes(prog)
    classes, types, multiclass, pact, third = {}, {}, {}, {}, {}
    for t in tables:
        title = (t.get("title") or "").strip()
        if title == "Multiclass Spellcaster: Spell Slots per Spell Level":
            multiclass = _slot_table(t) or {}
            continue
        m = re.fullmatch(r"(.+?) Features", title)
        if m:
            cls = m.group(1).strip().lower()
            if cls not in casters:
                continue
            cols = t.get("columns", [])
            if any(c.strip().lower() == "slot level" for c in cols):   # pact-magic shape
                types[cls] = "pact"
                iL = _col(cols, "Level"); iN = _col(cols, "Spell Slots"); iSL = _col(cols, "Slot Level")
                for r in t.get("rows", []):
                    lv, n, sl = (_int(r[iL]) if iL is not None else None,
                                 _int(r[iN]) if iN is not None and iN < len(r) else None,
                                 _int(r[iSL]) if iSL is not None and iSL < len(r) else None)
                    if lv and n and sl:
                        pact[str(lv)] = {"slots": n, "level": sl}
                continue
            tbl = _slot_table(t)
            if tbl and any(tbl.values()):
                classes[cls] = tbl
                top = max((int(k) for row in tbl.values() for k in row), default=0)
                types[cls] = "full" if top >= 6 else "half"
        elif title.endswith(" Spellcasting"):
            tbl = _slot_table(t)
            if tbl and any(tbl.values()):
                third[re.sub(r" Spellcasting$", "", title).strip().lower()] = tbl
    return {"classes": classes, "multiclass": multiclass, "pact": pact, "third": third}, types


def subclass_spells(tables):
    """Per subclass → {class_level: [always-prepared spell names]} from the '<Subclass> Spells' tables
    (keyed off a '<Class> Level' column). These grants are additive — they don't count toward the
    class's prepared-spell budget."""
    base_classes = {"bard", "cleric", "druid", "paladin", "ranger", "sorcerer", "warlock", "wizard"}
    out = {}
    for t in tables:
        ti = (t.get("title") or "").strip()
        if not ti.endswith(" Spells"):
            continue
        name = ti[:-len(" Spells")].strip()
        if re.match(r"(Cantrips|Level \d+)", name) or name.lower() in base_classes:
            continue
        cols = t.get("columns", [])
        if len(cols) < 2 or not cols[0].strip().lower().endswith("level"):
            continue
        by_level = {}
        for r in t.get("rows", []):
            lvl = _int(r[0]) if r else None
            if lvl is None or len(r) < 2:
                continue
            names = [x.strip() for x in r[1].split(",") if x.strip()]
            if names:
                by_level[str(lvl)] = names
        if by_level:
            out[name.lower()] = by_level
    return out


def multiclass_proficiencies(sections, class_prof):
    """Per class → the REDUCED proficiencies granted when the class is taken as a SECONDARY class,
    parsed from its 'As a Multiclass Character' grant list:
    {skills: {choose, from} | None, armor: [tokens], weapons: [tokens], tools: {fixed|choose} | None}.
    A class whose multiclass entry grants only a Hit Point Die (monk/sorcerer/wizard) gets all-empty
    grants. This is distinct from the FIRST (initial) class's full grant in class_proficiencies."""
    out = {}
    for s in sections:
        t = re.sub(r"\s+", " ", s.get("text") or "")
        # Grant list runs from "Core <Class> Traits table:" to the next "Gain the …" bullet. Anchor on
        # the "Gain the" text, not the bullet glyph (·/•/- vary and are unicode-fragile). The heading is
        # upper- or title-case across classes, and the "table:" colon form is the multiclass grant (the
        # level-1 block says "Gain all the traits … table." with no colon), so re.I is safe here.
        m = re.search(r"As a Multiclass Character.*?Core (\w+) Traits table:\s*(.*?)\s*Gain the", t, re.I)
        if not m:
            continue
        cls = m.group(1).strip().lower()
        grant = m.group(2)
        entry = {"skills": None, "armor": _category_tokens(grant, _ARMOR_TOKENS),
                 "weapons": _category_tokens(grant, _WEAPON_TOKENS), "tools": None}
        if re.search(r"proficiency in one skill", grant, re.I):
            from_own = re.search(r"from the .+? skill list", grant, re.I)
            own_from = ((class_prof.get(cls) or {}).get("skills") or {}).get("from")
            entry["skills"] = {"choose": 1, "from": own_from if from_own else None}
        if re.search(r"thieves['’]? tools", grant, re.I):
            entry["tools"] = {"fixed": ["Thieves' Tools"]}
        elif re.search(r"musical instrument", grant, re.I):
            entry["tools"] = {"choose": 1}
        out[cls] = entry
    # classes whose multiclass grant is Hit-Point-Die-only don't match the colon form → empty grant
    for cls in class_prof:
        out.setdefault(cls, {"skills": None, "armor": [], "weapons": [], "tools": None})
    return out


_CLASS_IDS = {"barbarian", "bard", "cleric", "druid", "fighter", "monk",
              "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard"}
_ABILITY_WORDS = "Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma"


def _feat_prereq(text):
    """Parse a feat's 'Prerequisite:' line into the checkable parts: {level, class, abilities}. Ability
    groups are any-of (e.g. 'Strength or Dexterity 13+' → [['str','dex']]). Non-score prerequisites
    (armour training, a spellcasting feature, an invocation) are left out — they aren't enforced yet."""
    m = re.search(r"Prerequisite:\s*([^)\n]+)", text)
    if not m:
        return None
    s = m.group(1)
    pre = {}
    cm = re.search(r"Level (\d+)\+\s+(\w+)", s)
    if cm and cm.group(2).lower() in _CLASS_IDS:
        pre["class"], pre["level"] = cm.group(2).lower(), int(cm.group(1))
    else:
        lm = re.search(r"Level (\d+)\+", s)
        if lm:
            pre["level"] = int(lm.group(1))
    for am in re.finditer(rf"((?:{_ABILITY_WORDS})(?:\s+or\s+(?:{_ABILITY_WORDS}))*)\s+13\+", s):
        group = [_ABILITY_IDS[w.lower()] for w in re.findall(_ABILITY_WORDS, am.group(1))]
        pre.setdefault("abilities", []).append(group)
    return pre or None


def feats(sections, tables):
    """Per feat → {category, repeatable, prereq?}. Category comes from the 'Feat List' tables; each
    feat has its own section (section name == feat name) carrying its Prerequisite / Repeatable text."""
    cats = {}
    for t in tables:
        if (t.get("title") or "").startswith(("Feat List", "Feats (continued")):
            for r in t.get("rows", []):
                if len(r) >= 2 and r[0].strip():
                    cats[r[0].strip().rstrip("*")] = r[1].strip()   # '*' in the list marks repeatable
    starred = {r[0].strip().rstrip("*") for t in tables
               if (t.get("title") or "").startswith(("Feat List", "Feats (continued"))
               for r in t.get("rows", []) if len(r) >= 2 and r[0].strip().endswith("*")}
    out = {}
    for s in sections:
        nm = (s.get("section") or "").strip()
        if nm not in cats:
            continue
        text = s.get("text") or ""
        entry = {"category": cats[nm],
                 "repeatable": nm in starred or bool(re.search(r"\bRepeatable\b", text))}
        pre = _feat_prereq(text)
        if pre:
            entry["prereq"] = pre
        out[nm.lower()] = entry
    return out


_CHOICE_COUNT_COLUMNS = {"eldritch invocations", "weapon mastery"}


def feature_choice_counts(tables):
    """Per class → {feature column → {level: count}} for features whose value is the NUMBER of choices
    the character makes (invocations known, weapons with a mastery). Resource columns (rages, points,
    uses) are excluded — they aren't 'pick N from a list'. Prose/subclass choice-counts (metamagic,
    maneuvers) are not mined here."""
    out = {}
    for t in tables:
        m = re.fullmatch(r"(.+?) Features", (t.get("title") or "").strip())
        if not m:
            continue
        cols = t.get("columns", [])
        iL = _col(cols, "Level")
        picks = {i: c.strip() for i, c in enumerate(cols) if c.strip().lower() in _CHOICE_COUNT_COLUMNS}
        if iL is None or not picks:
            continue
        cls = {}
        for r in t.get("rows", []):
            lvl = _int(r[iL]) if iL < len(r) else None
            if lvl is None:
                continue
            for i, header in picks.items():
                if i < len(r) and _int(r[i]) is not None:
                    cls.setdefault(header, {})[str(lvl)] = _int(r[i])
        if cls:
            out[m.group(1).strip().lower()] = cls
    return out


def caster_meta(sections):
    """Extra caster facts the spellcasting checks need, grounded in the rulebook:
    - spellbook: classes that prepare from a known pool (a Spellbook) — leveled spells may legally be
      unprepared for them;
    - arcanum: the pact caster's Mystic Arcanum ceiling {caster_level: max spell level} — spells cast
      without a slot above the pact slot level;
    - always_prepared: per-class class-feature spells that are always prepared and DON'T count against
      the prepared budget."""
    classes = {"barbarian", "bard", "cleric", "druid", "fighter", "monk",
               "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard"}
    spellbook, always = [], {}
    for s in sections:
        nm = (s.get("section") or "").strip().lower()
        if nm not in classes:
            continue
        text = s.get("text") or ""
        if "spellbook" in text.lower():
            spellbook.append(nm)
        sp = sorted(set(re.findall(r"always have the ([A-Z][\w' ]+?) spell prepared", text)))
        if sp:
            always[nm] = sp
    txt = "\n".join(s.get("text") or "" for s in sections)
    am = re.search(r"Mystic Arcanum.{0,600}", txt, re.S)
    block = am.group() if am else ""
    arcanum = {}
    if re.search(r"level 6 \w+ spell as this arcanum", block):
        arcanum["11"] = 6
    for lv, sl in re.findall(r"(\d+) \(level (\d+) spell\)", block):
        arcanum[lv] = int(sl)
    return {"spellbook": sorted(set(spellbook)), "arcanum": arcanum, "always_prepared": always}


def main():
    source = os.environ.get("SOURCE_JSON")
    out = os.environ.get("VALIDATOR_DATA_DIR_HOST")
    if not source or not out:
        raise SystemExit("build_rules: set SOURCE_JSON (reference source) and "
                         "VALIDATOR_DATA_DIR_HOST (output dir) in the environment")
    with open(source) as f:
        book = json.load(f)
    tables = _tables(book)
    os.makedirs(out, exist_ok=True)

    prog = class_progression(tables)
    with open(os.path.join(out, "class_progression.json"), "w") as f:
        json.dump(prog, f, indent=1)
    print(f"class_progression: {len(prog)} classes -> {out}/class_progression.json")

    bg = backgrounds(book["sections"])
    with open(os.path.join(out, "backgrounds.json"), "w") as f:
        json.dump(bg, f, indent=1)
    missing_skills = [b for b, v in bg.items() if not v.get("skills")]
    print(f"backgrounds: {len(bg)} -> {out}/backgrounds.json"
          + (f"  [!] no skills for: {missing_skills}" if missing_skills else "  (all have skills)"))

    lists = spell_lists(tables)
    with open(os.path.join(out, "spell_lists.json"), "w") as f:
        json.dump(lists, f, indent=1)
    print(f"spell_lists: {len(lists)} classes, {len({n for d in lists.values() for n in d})} spells "
          f"-> {out}/spell_lists.json")

    hd = class_hit_dice(tables)
    with open(os.path.join(out, "hit_dice.json"), "w") as f:
        json.dump(hd, f, indent=1)
    print(f"hit_dice: {len(hd)} classes -> {out}/hit_dice.json")

    prof = class_proficiencies(tables)
    mc = multiclass_proficiencies(book["sections"], prof)
    for cls, grant in mc.items():
        if cls in prof:
            prof[cls]["multiclass"] = grant
    with open(os.path.join(out, "class_proficiencies.json"), "w") as f:
        json.dump(prof, f, indent=1)
    print(f"class_proficiencies: {len(prof)} classes (+multiclass grants) -> {out}/class_proficiencies.json")

    slots, caster_types = spell_slots(tables, prog)
    with open(os.path.join(out, "spell_slots.json"), "w") as f:
        json.dump(slots, f, indent=1)
    print(f"spell_slots: {len(slots['classes'])} class tables, {len(slots['multiclass'])} multiclass rows, "
          f"{len(slots['pact'])} pact rows, {len(slots['third'])} third-caster tables -> {out}/spell_slots.json")

    with open(os.path.join(out, "caster_types.json"), "w") as f:
        json.dump(caster_types, f, indent=1)
    print(f"caster_types: {caster_types} -> {out}/caster_types.json")

    subs = subclass_spells(tables)
    with open(os.path.join(out, "subclass_spells.json"), "w") as f:
        json.dump(subs, f, indent=1)
    print(f"subclass_spells: {len(subs)} subclasses -> {out}/subclass_spells.json")

    ft = feats(book["sections"], tables)
    with open(os.path.join(out, "feats.json"), "w") as f:
        json.dump(ft, f, indent=1)
    n_pre = sum(1 for v in ft.values() if v.get("prereq"))
    n_rep = sum(1 for v in ft.values() if v["repeatable"])
    print(f"feats: {len(ft)} ({n_pre} with prereqs, {n_rep} repeatable) -> {out}/feats.json")

    fcc = feature_choice_counts(tables)
    with open(os.path.join(out, "feature_choice_counts.json"), "w") as f:
        json.dump(fcc, f, indent=1)
    print(f"feature_choice_counts: { {k: list(v) for k, v in fcc.items()} } -> {out}/feature_choice_counts.json")

    meta = caster_meta(book["sections"])
    with open(os.path.join(out, "caster_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"caster_meta: spellbook={meta['spellbook']} arcanum={meta['arcanum']} "
          f"always_prepared={ {k: len(v) for k, v in meta['always_prepared'].items()} } -> {out}/caster_meta.json")


if __name__ == "__main__":
    main()
