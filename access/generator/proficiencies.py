"""Proficiency- and expertise-CHOICE reads for the choice grammar: the choose-mode proficiency
grants (tool / language / skill-or-tool) and expertise-choice grants an owner carries, plus the
membership predicates a pick is validated against.

Pure DB reads only — no rule math. Aggregating a build's choice counts across its owners and gating
them by level belong to the grammar layer (``options.py``), not here.

**No option pool is ever emitted.** The candidate-value tables (``grant_proficiency_value`` /
``grant_expertise_value``) are the reference source's curated menus; they are read only for a
single-id MEMBERSHIP test (validate one pick) — never enumerated out. The category / language /
skill-or-tool kinds returned are the generic mechanic, not a source-specific list.
"""
from access.generator import GeneratorAccess


# --------------------------------------------------------------------------- proficiency choices
def proficiency_choice_grants(access: GeneratorAccess, owner_kind: str, owner_id: str,
                              target_kind: str) -> list:
    """The choose-mode proficiency grants an owner carries for one target kind, as
    (id, gained_at_level, choose_n, from_any, multiclass_only) rows ordered by id. `target_kind` is
    'tool', 'language', or 'skill_or_tool'. Empty when the owner has no such choice grant. Pure DB
    read — the grant's candidate pool is NOT returned (see the module note)."""
    return access.db.q(
        "SELECT id, gained_at_level, choose_n, from_any, multiclass_only "
        "FROM grant_proficiency WHERE owner_kind=? AND owner_id=? AND target_kind=? AND mode='choose' "
        "ORDER BY id", owner_kind, owner_id, target_kind)


def grant_tool_categories(access: GeneratorAccess, grant_id: str) -> list[str]:
    """The tool-category ids a tool-choice grant is restricted to, ordered. Empty when the grant is
    not category-restricted (a from-any grant or one carrying an explicit value pool). Pure DB read."""
    return [r["tool_category_id"] for r in access.db.q(
        "SELECT tool_category_id FROM grant_proficiency_category WHERE grant_id=? "
        "ORDER BY tool_category_id", grant_id)]


def value_in_grant(access: GeneratorAccess, grant_id: str, target_id: str) -> bool:
    """True when `target_id` is in a proficiency grant's candidate-value pool. A single-id membership
    test — the pool itself is never returned (liability)."""
    return access.db.scalar(
        "SELECT 1 FROM grant_proficiency_value WHERE grant_id=? AND target_id=? LIMIT 1",
        grant_id, target_id) is not None


def tool_in_categories(access: GeneratorAccess, tool_id: str, category_ids: list[str]) -> bool:
    """True when a tool belongs to any of the given tool categories (via the tool's own category id).
    A membership test only — the tools in a category are never enumerated. False for an empty
    category list."""
    if not category_ids:
        return False
    marks = ",".join("?" for _ in category_ids)
    return access.db.scalar(
        f"SELECT 1 FROM tool WHERE id=? AND tool_category_id IN ({marks}) LIMIT 1",
        tool_id, *category_ids) is not None


def is_language(access: GeneratorAccess, language_id: str) -> bool:
    """True when `language_id` is a language in the loaded ruleset. Membership test only."""
    return access.db.scalar(
        "SELECT 1 FROM language WHERE id=? LIMIT 1", language_id) is not None


def is_tool(access: GeneratorAccess, tool_id: str) -> bool:
    """True when `tool_id` is a tool in the loaded ruleset. Membership test only."""
    return access.db.scalar(
        "SELECT 1 FROM tool WHERE id=? LIMIT 1", tool_id) is not None


def is_skill(access: GeneratorAccess, skill_id: str) -> bool:
    """True when `skill_id` is a skill in the loaded ruleset. Membership test only."""
    return access.db.scalar(
        "SELECT 1 FROM skill WHERE id=? LIMIT 1", skill_id) is not None


# --------------------------------------------------------------------------- expertise choices
def expertise_choice_grants(access: GeneratorAccess, owner_kind: str, owner_id: str) -> list:
    """The choose-mode expertise grants an owner carries, as (id, gained_at_level, choose_n, mode)
    rows ordered by id. Only the two choose modes are returned — a fixed expertise grant is not a
    choice. Empty when the owner grants no expertise choice. Pure DB read."""
    return access.db.q(
        "SELECT id, gained_at_level, choose_n, mode FROM grant_expertise "
        "WHERE owner_kind=? AND owner_id=? AND mode<>'fixed' ORDER BY id", owner_kind, owner_id)


def expertise_has_value_pool(access: GeneratorAccess, grant_id: str) -> bool:
    """True when an expertise grant names a candidate skill pool (vs. 'any already-proficient skill').
    A COUNT>0 check — the pool itself is not returned."""
    return (access.db.scalar(
        "SELECT COUNT(*) FROM grant_expertise_value WHERE grant_id=?", grant_id) or 0) > 0


def expertise_value_in_grant(access: GeneratorAccess, grant_id: str, skill_id: str) -> bool:
    """True when `skill_id` is in an expertise grant's named candidate pool. A single-id membership
    test — the pool is never enumerated (liability)."""
    return access.db.scalar(
        "SELECT 1 FROM grant_expertise_value WHERE grant_id=? AND skill_id=? LIMIT 1",
        grant_id, skill_id) is not None
