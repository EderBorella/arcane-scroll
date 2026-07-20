"""Access-layer tests for the generator's proficiency- / expertise-CHOICE readers (F07 D3, T07/T08)
plus the equipment choice-item reader (T09).

Each reader is exercised against the synthetic content-neutral rules DB (the ``gen_access`` fixture
in tests/conftest.py). These are pure-read machinery tests — presence of choice grants, the category
restriction, and the single-id MEMBERSHIP predicates a pick is validated against. No reader ever
returns a candidate pool (the liability rule), so the tests assert membership booleans, not lists of
options. All ids are synthetic placeholders (``class-tl``, ``lang-a``, ``tool-x``, ``sk1`` …).
"""
from access.generator import equipment as equip_q
from access.generator import proficiencies as prof_q


# --- proficiency choice grants ---------------------------------------------

def test_proficiency_choice_grants_language(gen_access):
    rows = prof_q.proficiency_choice_grants(gen_access, "class", "class-tl", "language")
    assert [r["id"] for r in rows] == ["gpr-tl-lang"]
    r = rows[0]
    assert r["choose_n"] == 2 and r["from_any"] == 1 and r["gained_at_level"] == 2


def test_proficiency_choice_grants_tool_with_and_without_multiclass(gen_access):
    rows = prof_q.proficiency_choice_grants(gen_access, "class", "class-tl", "tool")
    ids = {r["id"]: r for r in rows}
    assert set(ids) == {"gpr-tl-tool", "gpr-tl-tool-mc"}
    assert ids["gpr-tl-tool"]["multiclass_only"] == 0
    assert ids["gpr-tl-tool-mc"]["multiclass_only"] == 1


def test_proficiency_choice_grants_empty_for_plain_class(gen_access):
    assert prof_q.proficiency_choice_grants(gen_access, "class", "class-a", "language") == []
    assert prof_q.proficiency_choice_grants(gen_access, "class", "class-a", "tool") == []


def test_grant_tool_categories(gen_access):
    assert prof_q.grant_tool_categories(gen_access, "gpr-tl-tool") == ["tc-music"]
    # a from-any language grant is not category-restricted
    assert prof_q.grant_tool_categories(gen_access, "gpr-tl-lang") == []


def test_tool_in_categories_membership_only(gen_access):
    assert prof_q.tool_in_categories(gen_access, "tool-x", ["tc-music"]) is True
    assert prof_q.tool_in_categories(gen_access, "tool-z", ["tc-music"]) is False  # NULL category
    assert prof_q.tool_in_categories(gen_access, "tool-x", []) is False


def test_kind_membership_predicates(gen_access):
    assert prof_q.is_language(gen_access, "lang-a") is True
    assert prof_q.is_language(gen_access, "tool-x") is False
    assert prof_q.is_tool(gen_access, "tool-x") is True
    assert prof_q.is_tool(gen_access, "lang-a") is False
    assert prof_q.is_skill(gen_access, "sk1") is True
    assert prof_q.is_skill(gen_access, "lang-a") is False


# --- expertise choice grants -----------------------------------------------

def test_expertise_choice_grants(gen_access):
    rows = prof_q.expertise_choice_grants(gen_access, "class", "class-tl")
    assert [r["id"] for r in rows] == ["gex-tl"]
    assert rows[0]["choose_n"] == 1 and rows[0]["mode"] == "choose_from_proficient"


def test_expertise_value_pool_membership(gen_access):
    # gex-tl names a pool {sk1, sk2}
    assert prof_q.expertise_has_value_pool(gen_access, "gex-tl") is True
    assert prof_q.expertise_value_in_grant(gen_access, "gex-tl", "sk1") is True
    assert prof_q.expertise_value_in_grant(gen_access, "gex-tl", "sk3") is False
    # gex-a (class-a) names no pool -> 'any already-proficient skill'
    assert prof_q.expertise_has_value_pool(gen_access, "gex-a") is False


# --- equipment choice-item reader (T09) ------------------------------------

def test_starting_equipment_choice_entries(gen_access):
    rows = equip_q.starting_equipment_choice_entries(gen_access, "sa-tl")
    kinds = [r["kind"] for r in rows]
    assert kinds == ["tool_category_choice", "focus_type_choice", "prof_choice_ref"]
    by_kind = {r["kind"]: r for r in rows}
    assert by_kind["tool_category_choice"]["tool_category_id"] == "tc-music"
    assert by_kind["focus_type_choice"]["focus_type_id"] == "ft-a"


def test_starting_equipment_choice_entries_excludes_item_and_gp(gen_access):
    # sa-a carries only a concrete item + gp -> no CHOICE entries
    assert equip_q.starting_equipment_choice_entries(gen_access, "sa-a") == []
