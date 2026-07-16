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


def feat_prereqs(access: GeneratorAccess, feat_id: str) -> list:
    """A feat's feat_prereq rows — (any_of_group, kind, min_level, ability_id, min_score,
    armor_category_id, note). AND across distinct any_of_group values, OR within a group; the
    grammar applies that grouping, this just returns the raw rows in a stable order (the row `id`
    is the final tie-break so rows sharing an any_of_group/kind — e.g. an OR of two ability
    prerequisites — keep a deterministic order)."""
    return access.db.q(
        "SELECT any_of_group, kind, min_level, ability_id, min_score, armor_category_id, note "
        "FROM feat_prereq WHERE feat_id=? ORDER BY any_of_group, kind, id", feat_id)
