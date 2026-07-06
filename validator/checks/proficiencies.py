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


def _secondary_class_contribution(classes: list, access) -> tuple[int, bool, set[str]]:
    """(budget, any_flag, pool) contributed by every class AFTER the first -- their reduced
    multiclass-only skill grants, not their full (primary-only) skill pool. Budget credits BOTH the
    fixed count and the choose_n of every multiclass skill grant (e.g. a rogue-style secondary class
    "choose 1 skill" grant) -- previously only fixed grants were credited, which false-flagged a
    fully-legal multiclass build as too-many-skill-proficiencies."""
    budget = 0
    any_flag = False
    pool: set[str] = set()
    for c in classes[1:]:
        if not isinstance(c, dict):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        c_any, c_fixed, c_choose_pool, c_choose_n = q.multiclass_skill_grants(access, cid)
        if c_any:
            any_flag = True
        budget += len(c_fixed) + c_choose_n
        pool |= set(c_fixed) | set(c_choose_pool)
    return budget, any_flag, pool


def _subclass_contribution(classes: list, access) -> tuple[int, bool, set[str]]:
    """(budget, any_flag, pool) contributed by every class entry's SUBCLASS skill grants (e.g. a
    College-of-Lore-style "choose 3 skills of your choice") -- same shape as the multiclass grants
    handled by `_secondary_class_contribution`: budget credits both the fixed count and the
    choose_n of every subclass skill grant, not just fixed values."""
    budget = 0
    any_flag = False
    pool: set[str] = set()
    for c in classes:
        if not isinstance(c, dict):
            continue
        sub = c.get("subclass")
        if not sub:
            continue
        sub_id = access.resolve("subclass", sub)
        if sub_id is None:
            continue
        # Gate the subclass's skill grant by the level of the class entry that owns it -- same
        # gained_at_level gating as the saving-throws check (most subclass skill grants are
        # level-3, but this keeps the two checks consistent and correct for any that aren't).
        c_level = c.get("level")
        c_at_level = c_level if isinstance(c_level, int) and not isinstance(c_level, bool) else 0
        s_any, s_fixed, s_choose_pool, s_choose_n = q.subclass_skill_grants(access, sub_id, at_level=c_at_level)
        if s_any:
            any_flag = True
        budget += len(s_fixed) + s_choose_n
        pool |= set(s_fixed) | set(s_choose_pool)
    return budget, any_flag, pool


def _legal_universe_and_budget(sheet: dict, ident: dict, classes: list, access) -> tuple[set[str], int, set[str]]:
    """(universe, budget, grant_only) -- `grant_only` is the subset of the universe that is legal
    *solely* because a species/feat grant confers it (not also reachable via the class pool or
    background). Those skills are automatically-conferred proficiencies, not picks spent against a
    choice pool, so a proficient sheet skill drawn only from that set must not count against the
    budget ceiling (it would otherwise produce a `too-many-skill-proficiencies` false positive for
    an otherwise-legitimate full class+background selection plus a granted skill)."""
    any_flag = False
    universe: set[str] = set()
    budget = 0

    first_class = _first_class(classes)
    n, class_any, class_pool = _class_contribution(first_class, access)
    budget += n
    any_flag = any_flag or class_any
    universe |= class_pool

    sec_budget, sec_any, sec_pool = _secondary_class_contribution(classes, access)
    budget += sec_budget
    any_flag = any_flag or sec_any
    universe |= sec_pool

    sub_budget, sub_any, sub_pool = _subclass_contribution(classes, access)
    budget += sub_budget
    any_flag = any_flag or sub_any
    universe |= sub_pool

    bg_id = access.resolve("background", ident.get("background"))
    if bg_id is not None:
        bg_skills = q.background_skills(access, bg_id)
        budget += len(bg_skills)
        universe |= set(bg_skills)

    base_universe = set(universe)

    # Grant sources (species + feats): a FIXED grant (mode='fixed') is an automatically-conferred
    # proficiency -- it widens legality but does not cost a budget slot (it lands in `granted_fixed`
    # and is excluded from the chargeable count below). A CHOOSE-mode grant (e.g. a feat like
    # "choose 1 skill of your choice", DB fact gpr-0120; or a species "choose 1 of {a,b,c}", DB fact
    # elf's gpr-0190; or "choose any skill", DB fact human's gpr-0193) is a real pick spent against
    # an ENLARGED budget -- it widens legality via `choose_pool`/any_flag but its choose_n is
    # credited to the budget directly, not folded into the free/automatic set.
    granted_fixed: set[str] = set()

    sp_id = access.resolve("species", ident.get("species"))
    if sp_id is not None:
        sp_any, sp_fixed, sp_choose_pool, sp_choose_n = q.grant_skill_sets(access, "species", sp_id)
        any_flag = any_flag or sp_any
        universe |= set(sp_fixed) | set(sp_choose_pool)
        granted_fixed |= set(sp_fixed)
        budget += sp_choose_n

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            feat_id = access.resolve("feat", f)
            if feat_id is None:
                continue
            f_any, f_fixed, f_choose_pool, f_choose_n = q.grant_skill_sets(access, "feat", feat_id)
            any_flag = any_flag or f_any
            universe |= set(f_fixed) | set(f_choose_pool)
            granted_fixed |= set(f_fixed)
            budget += f_choose_n

    grant_only = granted_fixed - base_universe

    if any_flag:
        universe = set(q.all_skill_ids(access))
    return universe, budget, grant_only


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
    if not isinstance(ident, dict):
        ident = {}
    raw_classes = ident.get("classes")
    classes = raw_classes if isinstance(raw_classes, list) else []

    universe, budget, grant_only = _legal_universe_and_budget(sheet, ident, classes, access)

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

    chargeable_count = len(proficient_ids - grant_only)
    if chargeable_count > budget:
        v.append(Violation(DOMAIN, "too-many-skill-proficiencies", "illegal",
                           f"{chargeable_count} proficient skills exceeds the budget of {budget}",
                           "skills"))

    # Expertise budget sums EVERY class's own grants at that class's own level (a rogue picked up
    # as a second class still grants its expertise, gated by the rogue's own level, not the first
    # class's) -- plus each class's subclass, plus feats (gated by total character level, since a
    # feat isn't tied to any one class's level track).
    ex_budget = 0
    total_level = 0
    for c in classes:
        if not isinstance(c, dict):
            continue
        c_level = c.get("level")
        c_at_level = c_level if isinstance(c_level, int) and not isinstance(c_level, bool) else 0
        total_level += c_at_level
        c_cid = access.resolve("class", c.get("class"))
        c_sub = c.get("subclass")
        c_sub_id = access.resolve("subclass", c_sub) if c_sub else None
        ex_budget += _expertise_budget(access, [("class", c_cid), ("subclass", c_sub_id)], c_at_level)

    feats = sheet.get("feats") if isinstance(sheet.get("feats"), list) else []
    feat_ids = [access.resolve("feat", f) for f in feats]
    ex_budget += _expertise_budget(access, [("feat", fid) for fid in feat_ids], total_level)

    for sid, k, path in expertise_picks:
        if sid not in proficient_ids:
            v.append(Violation(DOMAIN, "expertise-not-proficient", "illegal",
                               f"{k}: expertise requires proficiency in the same skill", path))

    if len(expertise_picks) > ex_budget:
        v.append(Violation(DOMAIN, "too-many-expertise", "illegal",
                           f"{len(expertise_picks)} expertise picks exceeds the budget of {ex_budget}",
                           "skills"))

    return v
