from access.db import RulesDB
from access.resolve import Resolver


def test_resolves_display_name_to_id(rules_db):
    r = Resolver(RulesDB(rules_db))
    assert r.resolve("class", "Class A") == "class-a"


def test_casing_and_whitespace_tolerant(rules_db):
    r = Resolver(RulesDB(rules_db))
    assert r.resolve("class", "  class a ") == "class-a"


def test_strips_parenthetical_qualifier(rules_db):
    r = Resolver(RulesDB(rules_db))
    assert r.resolve("class", "Class A (multiclass)") == "class-a"


def test_unknown_name_returns_none(rules_db):
    r = Resolver(RulesDB(rules_db))
    assert r.resolve("class", "Nope") is None
    assert r.resolve("class", None) is None


def test_unknown_dimension_raises(rules_db):
    import pytest
    r = Resolver(RulesDB(rules_db))
    with pytest.raises(ValueError):
        r.resolve("not_a_dim", "x")
