"""Proficiencies domain: skill and expertise legality against the first class's skill pool,
background skills, and species/feat grant sources. Armor/weapon/tool proficiency legality is out
of scope here (F05-T19 -- it needs multiclass-reduced grant modelling + noisy string resolution).

Skill legality uses the UNION of every legal source plus a budget ceiling, not exact per-skill
source attribution -- a declared `source` on a sheet skill is not checked against any one grant;
that is a deliberate simplification (see the plan). Every expectation is derived from the DB;
malformed sheet data becomes a structured finding rather than a raise."""
from access.validator import proficiencies as q
from validator.report import Violation

DOMAIN = "proficiencies"


def _first_class(classes: list) -> dict | None:
    if classes and isinstance(classes[0], dict):
        return classes[0]
    return None


def _class_contribution(first: dict | None, access) -> tuple[int, bool, set[str]]:
    """(budget, any_flag, pool) contributed by the first class, or a zero contribution if it's
    missing or unresolvable."""
    if first is None:
        return 0, False, set()
    cid = access.resolve("class", first.get("class"))
    if cid is None:
        return 0, False, set()
    n, from_any, pool = q.class_skill_pool(access, cid)
    return (n or 0), bool(from_any), set(pool)


def _legal_universe_and_budget(sheet: dict, ident: dict, first_class: dict | None, access) -> tuple[set[str], int]:
    any_flag = False
    universe: set[str] = set()
    budget = 0

    n, class_any, class_pool = _class_contribution(first_class, access)
    budget += n
    any_flag = any_flag or class_any
    universe |= class_pool

    bg_id = access.resolve("background", ident.get("background"))
    if bg_id is not None:
        bg_skills = q.background_skills(access, bg_id)
        budget += len(bg_skills)
        universe |= set(bg_skills)

    # Grant sources (species + feats) only widen legality -- they do not add to the budget, since
    # they are automatically-conferred proficiencies rather than picks spent against a choice pool.
    sp_id = access.resolve("species", ident.get("species"))
    if sp_id is not None:
        sp_any, sp_fixed = q.grant_skill_sets(access, "species", sp_id)
        any_flag = any_flag or sp_any
        universe |= set(sp_fixed)

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            feat_id = access.resolve("feat", f)
            if feat_id is None:
                continue
            f_any, f_fixed = q.grant_skill_sets(access, "feat", feat_id)
            any_flag = any_flag or f_any
            universe |= set(f_fixed)

    if any_flag:
        universe = set(q.all_skill_ids(access))
    return universe, budget


def _expertise_budget(access, owners: list[tuple[str, str | None]], at_level: int) -> int:
    budget = 0
    for owner_kind, owner_id in owners:
        if owner_id is None:
            continue
        for grant in q.expertise_grants(access, owner_kind, owner_id, at_level):
            choose_n = grant["choose_n"]
            if isinstance(choose_n, int) and not isinstance(choose_n, bool):
                budget += choose_n
    return budget


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    skills = sheet.get("skills")
    if skills is None:
        return v
    if not isinstance(skills, dict):
        v.append(Violation(DOMAIN, "malformed-skills", "illegal",
                           "skills must be a dict", "skills"))
        return v

    ident = sheet.get("identity", {}) or {}
    raw_classes = ident.get("classes")
    classes = raw_classes if isinstance(raw_classes, list) else []
    first_class = _first_class(classes)

    universe, budget = _legal_universe_and_budget(sheet, ident, first_class, access)

    proficient_ids: set[str] = set()
    expertise_picks: list[tuple[str, str, str]] = []   # (skill_id, key, path)
    for k, entry in skills.items():
        path = f"skills.{k}"
        sid = access.resolve("skill", k)
        if sid is None:
            v.append(Violation(DOMAIN, "unknown-skill", "illegal",
                               f"unknown skill: {k!r}", path))
            continue
        if not isinstance(entry, dict):
            continue

        if entry.get("proficient"):
            proficient_ids.add(sid)
            if sid not in universe:
                v.append(Violation(DOMAIN, "skill-not-legal", "illegal",
                                   f"{k}: not a legal skill proficiency for this build", path))
        if entry.get("expertise"):
            expertise_picks.append((sid, k, path))

    if len(proficient_ids) > budget:
        v.append(Violation(DOMAIN, "too-many-skill-proficiencies", "illegal",
                           f"{len(proficient_ids)} proficient skills exceeds the budget of {budget}",
                           "skills"))

    level = first_class.get("level") if first_class is not None else None
    at_level = level if isinstance(level, int) and not isinstance(level, bool) else 0
    cid = access.resolve("class", first_class.get("class")) if first_class is not None else None
    sub = first_class.get("subclass") if first_class is not None else None
    sub_id = access.resolve("subclass", sub) if sub else None
    feats = sheet.get("feats") if isinstance(sheet.get("feats"), list) else []
    feat_ids = [access.resolve("feat", f) for f in feats]

    ex_budget = _expertise_budget(
        access, [("class", cid), ("subclass", sub_id)] + [("feat", fid) for fid in feat_ids], at_level)

    for sid, k, path in expertise_picks:
        if sid not in proficient_ids:
            v.append(Violation(DOMAIN, "expertise-not-proficient", "illegal",
                               f"{k}: expertise requires proficiency in the same skill", path))

    if len(expertise_picks) > ex_budget:
        v.append(Violation(DOMAIN, "too-many-expertise", "illegal",
                           f"{len(expertise_picks)} expertise picks exceeds the budget of {ex_budget}",
                           "skills"))

    return v
