"""Layer: proficiencies & skills. Saving-throw, armour, weapon and (fixed) tool proficiencies come
from the FIRST class (RAW); class-granted skills must number the class's 'choose N' and be drawn from
its list; a background's granted skills must all be present; and expertise must sit on a proficient
skill and not exceed what the character's classes grant. Collects all findings; never raises."""
from validator.report import Violation, WARNING

LAYER = "proficiencies"

_ARMOR_VOCAB = ("light", "medium", "heavy", "shield")
_WEAPON_VOCAB = ("simple", "martial")


def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _prof_tokens(values, vocab):
    """Normalise a sheet proficiency list (display names) to closed-vocabulary category tokens;
    'All armor' expands to light/medium/heavy."""
    toks = set()
    for v in values or []:
        low = str(v).lower()
        if "all" in low and "armor" in low:
            toks |= {"light", "medium", "heavy"}
        for t in vocab:
            if t in low:
                toks.add("shields" if t == "shield" else t)
    return toks


def check(sheet, rules):
    out = []
    classes = (sheet.get("identity") or {}).get("classes") or []
    if not classes:
        return out
    first = classes[0].get("class")

    exp_saves = rules.class_saves(first)
    if exp_saves:
        prof = {ab for ab, v in (sheet.get("saving_throws") or {}).items() if v.get("proficient")}
        missing = [ab for ab in exp_saves if ab not in prof]      # extras are legal (Resilient, etc.)
        if missing:
            out.append(Violation(LAYER, "saving_throws",
                                 f"missing save proficiency {missing} from the first class {first} "
                                 f"(has {sorted(prof)})", sorted(exp_saves), sorted(prof)))

    # Class skills: the first class grants its full "choose N"; each SUBSEQUENT class grants only its
    # reduced multiclass skill (0, or 1 from its own list / any). Count + on-list are checked against
    # the combined budget and the union of the applicable lists (the sheet doesn't attribute a class
    # skill to a specific class, so this is the tightest sound check).
    cs = rules.class_skills(first)
    if cs:
        class_skills = [k for k, v in (sheet.get("skills") or {}).items()
                        if v.get("source") == "class" and v.get("proficient")]
        expected = cs.get("choose")
        any_list = cs.get("from") is None                          # None ⇒ choose from any skill
        allowed = {_norm(o) for o in (cs.get("from") or [])}
        for c in classes[1:]:
            mcs = (rules.class_multiclass(c.get("class")) or {}).get("skills")
            if not mcs:
                continue
            if expected is not None and mcs.get("choose") is not None:
                expected += mcs["choose"]
            if mcs.get("from") is None:
                any_list = True
            else:
                allowed |= {_norm(o) for o in mcs["from"]}
        if expected is not None and len(class_skills) != expected:
            out.append(Violation(LAYER, "skill_count",
                                 f"{len(class_skills)} class skill(s); the character's classes grant {expected}",
                                 expected, len(class_skills)))
        if not any_list and allowed:
            off = sorted(s for s in class_skills if _norm(s) not in allowed)
            if off:
                out.append(Violation(LAYER, "skill_off_list",
                                     f"class skills {off} not on any of the character's class skill lists",
                                     sorted(allowed), off))

    bg = (sheet.get("identity") or {}).get("background")
    bg_skills = rules.background_skills(bg)
    if bg_skills:
        proficient = {_norm(k) for k, v in (sheet.get("skills") or {}).items() if v.get("proficient")}
        missing = [s for s in bg_skills if _norm(s) not in proficient]
        if missing:
            out.append(Violation(LAYER, "background_skills_missing",
                                 f"background '{bg}' grants {bg_skills}; missing {missing}", bg_skills, missing))

    prof = sheet.get("proficiencies") or {}

    exp_armor = rules.class_armor(first)
    if exp_armor:
        have = _prof_tokens(prof.get("armor"), _ARMOR_VOCAB)
        missing = [t for t in exp_armor if t not in have]
        if missing:
            out.append(Violation(LAYER, "armor_proficiency_missing",
                                 f"{first} grants armour {exp_armor}; missing {missing}",
                                 exp_armor, sorted(have)))

    exp_weapons = rules.class_weapons(first)
    if exp_weapons:
        have = _prof_tokens(prof.get("weapons"), _WEAPON_VOCAB)
        missing = [t for t in exp_weapons if t not in have]
        if missing:
            out.append(Violation(LAYER, "weapon_proficiency_missing",
                                 f"{first} grants weapons {exp_weapons}; missing {missing}",
                                 exp_weapons, sorted(have)))

    tools = rules.class_tools(first)
    if tools and tools.get("fixed"):
        have = {_norm(t) for t in prof.get("tools") or []}
        missing = [t for t in tools["fixed"] if _norm(t) not in have]
        if missing:
            out.append(Violation(LAYER, "tool_proficiency_missing",
                                 f"{first} grants tools {tools['fixed']}; missing {missing}",
                                 tools["fixed"], sorted(prof.get("tools") or [])))

    skills = sheet.get("skills") or {}
    for name, v in skills.items():
        if v.get("expertise") and not v.get("proficient"):
            out.append(Violation(LAYER, "expertise_without_proficiency",
                                 f"skill '{name}' has expertise but is not proficient", True, False))

    n_expertise = sum(1 for v in skills.values() if v.get("expertise"))
    granted, known = 0, True
    for c in classes:
        g = rules.expertise_granted(c.get("class"), c.get("level") or 0)
        if g is None:
            known = False
        else:
            granted += g
    if known and n_expertise > granted:
        out.append(Violation(LAYER, "expertise_over_grant",
                             f"{n_expertise} expertise skill(s); classes grant {granted} "
                             f"(any extra would have to be feat-granted)", granted, n_expertise,
                             severity=WARNING))
    return out
