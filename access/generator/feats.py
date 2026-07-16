"""Feat-domain option reads for the choice grammar: the feat catalogue (optionally narrowed to one
category, e.g. the origin feats a background/species grants vs the general feats an ability-increase
slot may take) plus a feat's prerequisite rows. Pure DB reads — no rule math (the prerequisite
grouping and gating live in the grammar)."""
from access.generator import GeneratorAccess


def list_feats(access: GeneratorAccess, category: str | None = None) -> list:
    """Feats the grammar may choose, as (id, name, category, repeatable) rows ordered by id. If
    `category` is given (e.g. 'origin', 'general', 'fighting-style', 'epic-boon'), only feats in that
    category are returned."""
    if category is not None:
        return access.db.q(
            "SELECT id, name, category, repeatable FROM feat WHERE category=? ORDER BY id", category)
    return access.db.q("SELECT id, name, category, repeatable FROM feat ORDER BY id")


def is_repeatable(access: GeneratorAccess, feat_id: str) -> bool:
    """True if the feat may be taken more than once (the raw ability-score-increase is repeatable, so
    a multi-slot build may spend several slots on it). Unknown feats are treated as non-repeatable."""
    return bool(access.db.scalar("SELECT repeatable FROM feat WHERE id=?", feat_id))


def ability_increase_grant(access: GeneratorAccess, feat_id: str) -> dict | None:
    """A feat's ability-score-increase grant, as ``{points, max_per_ability, from_any, abilities}``,
    or None when the feat confers no increase. ``abilities`` is the specific ability ids the increase
    may target (empty when ``from_any`` is set — the increase may go to any ability). Pure DB read;
    which ability to raise (when there is a choice) is the allocator's job, not this reader's.

    The grant's ``cap`` and ``condition_kind`` columns are intentionally NOT surfaced: the standard
    score cap is applied by the CORE deriver (which reads it once, per ruleset), and no feat-slot
    increase in this ruleset is conditional — so exposing them here would only invite a consumer to
    re-implement cap/condition handling that already lives downstream."""
    row = access.db.one(
        "SELECT id, points, max_per_ability, from_any FROM grant_ability_increase "
        "WHERE owner_kind='feat' AND owner_id=?", feat_id)
    if row is None:
        return None
    abilities = [r["ability_id"] for r in access.db.q(
        "SELECT ability_id FROM grant_ability_increase_value WHERE grant_id=? ORDER BY ability_id",
        row["id"])]
    return {"points": row["points"], "max_per_ability": row["max_per_ability"],
            "from_any": row["from_any"], "abilities": abilities}


def feat_prereqs(access: GeneratorAccess, feat_id: str) -> list:
    """A feat's feat_prereq rows — (any_of_group, kind, min_level, ability_id, min_score,
    armor_category_id, note). AND across distinct any_of_group values, OR within a group; the
    grammar applies that grouping, this just returns the raw rows in a stable order (the row `id`
    is the final tie-break so rows sharing an any_of_group/kind — e.g. an OR of two ability
    prerequisites — keep a deterministic order)."""
    return access.db.q(
        "SELECT any_of_group, kind, min_level, ability_id, min_score, armor_category_id, note "
        "FROM feat_prereq WHERE feat_id=? ORDER BY any_of_group, kind, id", feat_id)
