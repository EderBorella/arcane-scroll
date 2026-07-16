"""Background-domain option reads for the choice grammar: the background catalogue plus each
background's ability-increase options, fixed skills, and origin-feat grant. Pure DB reads — no rule
math."""
from access.generator import GeneratorAccess


def list_backgrounds(access: GeneratorAccess) -> list:
    """Every background the grammar may choose, as (id, name, feat_id, feat_choice, tool_id,
    tool_category_id) rows, ordered by id."""
    return access.db.q(
        "SELECT id, name, feat_id, feat_choice, tool_id, tool_category_id FROM background ORDER BY id")


def background_ability_options(access: GeneratorAccess, background_id: str) -> list[str]:
    """The ability ids a background may increase, in the background's declared ordinal order
    (ability_id as a secondary tie-break to lock determinism)."""
    return [r["ability_id"] for r in access.db.q(
        "SELECT ability_id FROM background_ability WHERE background_id=? ORDER BY ordinal, ability_id",
        background_id)]


def background_skills(access: GeneratorAccess, background_id: str) -> list[str]:
    """The fixed skill ids a background grants, ordered by skill_id."""
    return [r["skill_id"] for r in access.db.q(
        "SELECT skill_id FROM background_skill WHERE background_id=? ORDER BY skill_id", background_id)]


def background_origin_feat(access: GeneratorAccess, background_id: str) -> tuple[str, object] | None:
    """(feat_id, feat_choice) the background confers as its origin feat, or None if it grants none.
    `feat_choice` qualifies a feat that itself carries a sub-choice (which list/option), or None."""
    row = access.db.one(
        "SELECT feat_id, feat_choice FROM background WHERE id=?", background_id)
    if row is None or row["feat_id"] is None:
        return None
    return row["feat_id"], row["feat_choice"]
