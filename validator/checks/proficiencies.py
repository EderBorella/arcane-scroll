"""Layer: proficiencies & skills (2024). Saving-throw proficiencies come from the FIRST class; and the
class-granted skills must number the class's 'choose N' and be drawn from its skill list. (Background
skills / expertise are later increments.) Collects all findings; never raises."""
from validator.report import Violation

LAYER = "proficiencies"


def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def check(sheet, rules):
    out = []
    classes = (sheet.get("identity") or {}).get("classes") or []
    if not classes:
        return out
    first = classes[0].get("class")

    exp_saves = rules.class_saves(first)
    if exp_saves:
        prof = {ab for ab, v in (sheet.get("saving_throws") or {}).items() if v.get("proficient")}
        if prof != set(exp_saves):
            out.append(Violation(LAYER, "saving_throws",
                                 f"save proficiencies {sorted(prof)} != {first}'s {sorted(exp_saves)}",
                                 sorted(exp_saves), sorted(prof)))

    cs = rules.class_skills(first)
    if cs:
        class_skills = [k for k, v in (sheet.get("skills") or {}).items()
                        if v.get("source") == "class" and v.get("proficient")]
        choose = cs.get("choose")
        if choose is not None and len(class_skills) != choose:
            out.append(Violation(LAYER, "skill_count",
                                 f"{len(class_skills)} class skill(s); {first} grants {choose}",
                                 choose, len(class_skills)))
        options = cs.get("from")
        if options:
            allowed = {_norm(o) for o in options}
            off = sorted(s for s in class_skills if _norm(s) not in allowed)
            if off:
                out.append(Violation(LAYER, "skill_off_list",
                                     f"class skills {off} not on {first}'s list", options, off))
    return out
