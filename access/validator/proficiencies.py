"""Proficiencies-domain DB facts: class skill pools, background skills, and the skill/expertise
grant spine (species/feat/subclass "you also gain proficiency in ..." rows). Armor/weapon/tool
proficiency legality is out of scope here (F05-T19)."""
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


def grant_skill_sets(access: ValidatorAccess, owner_kind: str, owner_id: str) -> tuple[bool, list[str]]:
    """(any_flag, fixed_skill_ids) over an owner's grant_proficiency rows with target_kind='skill'.
    `any_flag` is True if any such grant confers "any skill" (from_any=1, or a choose-mode grant with
    no fixed value pool); `fixed_skill_ids` is the union of grant_proficiency_value.target_id across
    the rest (whether the grant is an unconditional fixed skill or a choose-from-a-limited-pool one --
    either way it just widens what's legal, per the union+budget simplification for this domain)."""
    any_flag = False
    fixed: set[str] = set()
    for header in primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id):
        if header["target_kind"] != "skill":
            continue
        values = [row["target_id"] for row in
                  primitives.children_of(access.db, "grant_proficiency", header["id"])
                  .get("grant_proficiency_value", [])]
        if header["from_any"] or (header["mode"] == "choose" and not values):
            any_flag = True
        else:
            fixed.update(values)
    return any_flag, sorted(fixed)


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
