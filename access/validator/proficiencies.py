"""Proficiencies-domain DB facts: class skill pools, background skills, and the skill/expertise
grant spine (species/feat/subclass "you also gain proficiency in ..." rows), plus armor/weapon/tool
proficiency queries (F05-T19)."""
from access import primitives
from access.validator import ValidatorAccess


def class_skill_pool(access: ValidatorAccess, class_id: str) -> tuple[int | None, int | None, list[str]]:
    """(skill_choose_n, skill_from_any, pool) for a class. `pool` is the explicit
    class_skill_option rows for the class -- empty for a class with skill_from_any=1, which has
    no rows (any skill is legal for it instead)."""
    row = access.db.one("SELECT skill_choose_n, skill_from_any FROM class WHERE id=?", class_id)
    if row is None:
        return None, None, []
    pool = [r["skill_id"] for r in access.db.q(
        "SELECT skill_id FROM class_skill_option WHERE class_id=?", class_id)]
    return row["skill_choose_n"], row["skill_from_any"], pool


def all_skill_ids(access: ValidatorAccess) -> list[str]:
    """Every skill id in the rulebook."""
    return [row["id"] for row in access.db.q("SELECT id FROM skill")]


def background_skills(access: ValidatorAccess, background_id: str) -> list[str]:
    """The fixed skill ids a background grants."""
    return [row["skill_id"] for row in access.db.q(
        "SELECT skill_id FROM background_skill WHERE background_id=?", background_id)]


def _split_skill_grants(access: ValidatorAccess, headers: list) -> tuple[bool, list[str], list[str], int]:
    """Shared fan-out for a set of grant_proficiency header rows with target_kind='skill':
    (any_flag, fixed_skill_ids, choose_pool_skill_ids, choose_n).

    `any_flag` is True if any grant confers "any skill" (from_any=1, or a choose-mode grant with no
    value pool). `fixed_skill_ids` is the union of values from unconditional (mode='fixed') grants --
    automatically-conferred proficiencies that cost no budget. `choose_pool_skill_ids` is the union
    of values from a choose-mode grant that DOES restrict to a limited pool (e.g. species-a-style
    "choose 1 of {a,b,c}", DB fact: elf's gpr-0190 choosing 1 of insight/perception/survival) --
    these widen legality but, unlike fixed grants, are real picks. `choose_n` is the sum of choose_n
    across every choose-mode grant (whether its pool is limited or unrestricted, e.g. rogue's
    multiclass gpr-0382 or human's species gpr-0193) -- the number of budget slots those grants
    actually cost, previously dropped on the floor entirely (a choose-mode grant is a pick spent
    against an enlarged budget, not a free, automatically-conferred proficiency)."""
    any_flag = False
    fixed: set[str] = set()
    choose_pool: set[str] = set()
    choose_n_total = 0
    for header in headers:
        if header["target_kind"] != "skill":
            continue
        values = [row["target_id"] for row in
                  primitives.children_of(access.db, "grant_proficiency", header["id"])
                  .get("grant_proficiency_value", [])]
        is_choose = header["mode"] == "choose"
        if header["from_any"] or (is_choose and not values):
            any_flag = True
        elif is_choose:
            choose_pool.update(values)
        else:
            fixed.update(values)
        if is_choose:
            n = header["choose_n"]
            if isinstance(n, int) and not isinstance(n, bool):
                choose_n_total += n
    return any_flag, sorted(fixed), sorted(choose_pool), choose_n_total


def grant_skill_sets(access: ValidatorAccess, owner_kind: str, owner_id: str) -> tuple[bool, list[str], list[str], int]:
    """(any_flag, fixed_skill_ids, choose_pool_skill_ids, choose_n) over an owner's grant_proficiency
    rows with target_kind='skill' -- see `_split_skill_grants` for the field semantics."""
    headers = primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id)
    return _split_skill_grants(access, headers)


def multiclass_skill_grants(access: ValidatorAccess, class_id: str) -> tuple[bool, list[str], list[str], int]:
    """(any_flag, fixed_skill_ids, choose_pool_skill_ids, choose_n) over a class's grant_proficiency
    skill rows marked multiclass_only=1 -- the reduced skill set a class confers when taken as a
    secondary (non-first) class in a multiclass build, as opposed to its full primary-class skill
    pool. See `_split_skill_grants` for the field semantics."""
    headers = [h for h in primitives.grants_for(access.db, "grant_proficiency", "class", class_id)
               if h["multiclass_only"]]
    return _split_skill_grants(access, headers)


def subclass_skill_grants(access: ValidatorAccess, subclass_id: str,
                          at_level: int | None = None) -> tuple[bool, list[str], list[str], int]:
    """(any_flag, fixed_skill_ids, choose_pool_skill_ids, choose_n) over a subclass's
    grant_proficiency skill rows (owner_kind='subclass') -- e.g. College of Lore's "choose 3
    skills of your choice". If `at_level` is given, only rows gained at or below it are included
    (a NULL gained_at_level always applies), so a level-gated subclass grant isn't credited before
    the character's class level reaches it. See `_split_skill_grants` for the field semantics."""
    headers = primitives.grants_for(access.db, "grant_proficiency", "subclass", subclass_id, at_level)
    return _split_skill_grants(access, headers)


def masterable_weapon_ids(access: ValidatorAccess) -> set[str]:
    """Weapons that have a mastery property (non-NULL mastery_id). Returns lowercased id + name."""
    rows = access.db.q(
        "SELECT w.id, ci.name FROM weapon w "
        "JOIN catalog_item ci ON w.id = ci.id "
        "WHERE w.mastery_id IS NOT NULL"
    )
    names: set[str] = set()
    for row in rows:
        names.add(row["id"].lower())
        names.add(row["name"].lower())
    return names


def expertise_grants(access: ValidatorAccess, owner_kind: str, owner_id: str, at_level: int) -> list[dict]:
    """grant_expertise rows for an owner gained at or below `at_level`, each as
    {choose_n, mode, skill_id, values} where `values` is the resolved grant_expertise_value pool
    (empty when the grant doesn't restrict to specific skills)."""
    out = []
    for header in primitives.grants_for(access.db, "grant_expertise", owner_kind, owner_id, at_level):
        values = [row["skill_id"] for row in
                  primitives.children_of(access.db, "grant_expertise", header["id"])
                  .get("grant_expertise_value", [])]
        out.append({
            "choose_n": header["choose_n"],
            "mode": header["mode"],
            "skill_id": header["skill_id"],
            "values": values,
        })
    return out


def armor_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                 at_level: int | None = None) -> list:
    """grant_proficiency rows with target_kind='armor_category' for an owner."""
    rows = primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id, at_level)
    return [r for r in rows if r["target_kind"] == "armor_category"]


def weapon_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                  at_level: int | None = None) -> list:
    """grant_proficiency rows with target_kind='weapon_tier' for an owner."""
    rows = primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id, at_level)
    return [r for r in rows if r["target_kind"] == "weapon_tier"]


def tool_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                at_level: int | None = None) -> list:
    """grant_proficiency rows with target_kind='tool' for an owner."""
    rows = primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id, at_level)
    return [r for r in rows if r["target_kind"] == "tool"]


def grant_values(access: ValidatorAccess, grant_id: str) -> list[str]:
    """target_id values from grant_proficiency_value for a grant header."""
    return [r["target_id"] for r in
            primitives.children_of(access.db, "grant_proficiency", grant_id)
            .get("grant_proficiency_value", [])]


def grant_categories(access: ValidatorAccess, grant_id: str) -> list[str]:
    """tool_category_id values from grant_proficiency_category for a grant header."""
    return [r["tool_category_id"] for r in
            primitives.children_of(access.db, "grant_proficiency", grant_id)
            .get("grant_proficiency_category", [])]


def armor_category_ids(access: ValidatorAccess) -> list[str]:
    """All armor_category IDs in the rulebook."""
    return [r["id"] for r in access.db.q("SELECT id FROM armor_category")]


def weapon_tier_ids(access: ValidatorAccess) -> list[str]:
    """All weapon_tier IDs in the rulebook."""
    return [r["id"] for r in access.db.q("SELECT id FROM weapon_tier")]


def tool_ids(access: ValidatorAccess) -> list[str]:
    """All tool IDs from the tool table."""
    return [r["id"] for r in access.db.q("SELECT id FROM tool")]


def tool_category_tools(access: ValidatorAccess, category_id: str) -> list[str]:
    """All tool IDs in a given tool_category."""
    return [r["id"] for r in access.db.q(
        "SELECT id FROM tool WHERE tool_category_id=?", category_id)]
