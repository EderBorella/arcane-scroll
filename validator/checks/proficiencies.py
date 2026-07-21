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
    fixed count and the choose_n of every multiclass skill grant (e.g. a secondary class's
    "choose 1 skill" multiclass grant) -- previously only fixed grants were credited, which false-flagged a
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
    # gpr-0190; or "choose any skill", DB fact gpr-0193) is a real pick spent against
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


def _level_of(c: dict) -> int:
    """A class entry's level as a non-negative int (0 for a missing / non-int level)."""
    lv = c.get("level")
    return lv if isinstance(lv, int) and not isinstance(lv, bool) else 0


def _choose_and_fixed_tool_language(ident: dict, classes: list, access) -> tuple[int, int, int]:
    """Re-derive, independently from DB facts, the CHOICE counts a build must fill for languages
    and tools: ``(language_choose_n, tool_choose_n, tool_fixed_count)``.

    Mirrors the choice-grammar's owner walk WITHOUT importing it (the two-layer doctrine): a class
    contributes its ``multiclass_only=0`` grants only as the FIRST class and its ``multiclass_only=1``
    grants only as a SECONDARY class; subclasses are level-gated at their class's level; background /
    species are gated at the total build level, and their fixed tools are ungated (as the CORE deriver
    materialises them). ``tool_fixed_count`` is the number of distinct fixed tool proficiencies the
    build automatically holds — the baseline a complete sheet lists on top of its tool CHOICES."""
    total_level = sum(_level_of(c) for c in classes if isinstance(c, dict))
    lang_choose = 0
    tool_choose = 0
    tool_fixed: set[str] = set()

    for i, c in enumerate(classes):
        if not isinstance(c, dict):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        level = _level_of(c)
        is_first = (i == 0)
        for g in q.language_grants(access, "class", cid, level):
            if g["mode"] == "choose" and bool(g["multiclass_only"]) == (not is_first):
                lang_choose += g["choose_n"] or 0
        for g in q.tool_grants(access, "class", cid, level):
            if bool(g["multiclass_only"]) != (not is_first):
                continue
            if g["mode"] == "choose":
                tool_choose += g["choose_n"] or 0
            elif g["mode"] == "fixed":
                tool_fixed |= set(q.grant_values(access, g["id"]))
        sub = c.get("subclass")
        sub_id = access.resolve("subclass", sub) if sub else None
        if sub_id is not None:
            for g in q.language_grants(access, "subclass", sub_id, level):
                if g["mode"] == "choose":
                    lang_choose += g["choose_n"] or 0
            for g in q.tool_grants(access, "subclass", sub_id, level):
                if g["mode"] == "choose":
                    tool_choose += g["choose_n"] or 0
                elif g["mode"] == "fixed":
                    tool_fixed |= set(q.grant_values(access, g["id"]))

    bg_id = access.resolve("background", ident.get("background"))
    sp_id = access.resolve("species", ident.get("species"))
    for owner_kind, owner_id in (("background", bg_id), ("species", sp_id)):
        if owner_id is None:
            continue
        for g in q.language_grants(access, owner_kind, owner_id, total_level):
            if g["mode"] == "choose":
                lang_choose += g["choose_n"] or 0
        for g in q.tool_grants(access, owner_kind, owner_id, total_level):
            if g["mode"] == "choose":
                tool_choose += g["choose_n"] or 0
        for g in q.tool_grants(access, owner_kind, owner_id):
            if g["mode"] == "fixed":
                tool_fixed |= set(q.grant_values(access, g["id"]))
    if bg_id is not None:
        bg_tool = q.background_tool_id(access, bg_id)
        if bg_tool:
            tool_fixed.add(bg_tool)

    return lang_choose, tool_choose, len(tool_fixed)


def _underfill(domain_code: str, resource: str, required: int, filled: int,
               path: str) -> Violation | None:
    """An ``incomplete`` under-fill finding when a required choice is short, else None. Message is
    generic (a resource kind + counts) — no source-specific names."""
    if filled >= required:
        return None
    missing = required - filled
    return Violation(DOMAIN, domain_code, "incomplete",
                     f"{filled} of {required} {resource} chosen — {missing} still to pick", path)


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    skills = sheet.get("skills")
    skills_malformed = skills is not None and not isinstance(skills, dict)
    if skills_malformed:
        v.append(Violation(DOMAIN, "malformed-skills", "illegal",
                           "skills must be a dict", "skills"))

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    raw_classes = ident.get("classes")
    classes = raw_classes if isinstance(raw_classes, list) else []

    if not skills_malformed:
        skills_dict = skills if isinstance(skills, dict) else {}
        universe, budget, grant_only = _legal_universe_and_budget(sheet, ident, classes, access)

        proficient_ids: set[str] = set()
        expertise_picks: list[tuple[str, str, str]] = []   # (skill_id, key, path)
        for k, entry in skills_dict.items():
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
        # Under-fill (G5): fewer chosen skill proficiencies than the build's budget is INCOMPLETE,
        # not illegal — the choice is still open. Symmetric with the over-fill above, off the same
        # independently-derived budget.
        if budget > 0:
            under = _underfill("too-few-skill-proficiencies", "skill proficiencies",
                               budget, chargeable_count, "skills")
            if under is not None:
                v.append(under)

        # Expertise budget sums EVERY class's own grants at that class's own level (a class picked up
        # as a second class still grants its expertise, gated by that class's own level, not the first
        # class's) -- plus each class's subclass, plus feats (gated by total character level, since a
        # feat isn't tied to any one class's level track).
        ex_budget = 0
        total_level = 0
        for c in classes:
            if not isinstance(c, dict):
                continue
            c_at_level = _level_of(c)
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
        if ex_budget > 0:
            under = _underfill("too-few-expertise", "expertise picks",
                               ex_budget, len(expertise_picks), "skills")
            if under is not None:
                v.append(under)

    # Language / tool CHOICE under-fill (G5), re-derived independently from the grant spine. A tool
    # gap is flagged only when the build actually HAS a tool choice (choose_n>0): a pure fixed-tool
    # shortfall stays out of scope (tool-proficiency legality is deferred, F05-T19). Languages carry
    # no fixed baseline on the sheet, so the required count is the choose count alone.
    lang_choose, tool_choose, tool_fixed_count = _choose_and_fixed_tool_language(ident, classes, access)

    if lang_choose > 0:
        present_langs = sheet.get("languages")
        present_langs = len(present_langs) if isinstance(present_langs, list) else 0
        under = _underfill("too-few-languages", "language choices", lang_choose, present_langs,
                           "languages")
        if under is not None:
            v.append(under)

    if tool_choose > 0:
        profs = sheet.get("proficiencies")
        raw_tools = profs.get("tools") if isinstance(profs, dict) else None
        present_tools = len(raw_tools) if isinstance(raw_tools, list) else 0
        required_tools = tool_fixed_count + tool_choose
        under = _underfill("too-few-tool-proficiencies", "tool proficiencies", required_tools,
                           present_tools, "proficiencies.tools")
        if under is not None:
            v.append(under)

    return v
