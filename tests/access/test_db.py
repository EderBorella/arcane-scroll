"""Sanity tests for the read-only connection handle."""
import sqlite3

import pytest

from access.db import ENV_VAR, RulesDB, resolve_path


def test_resolve_path_prefers_argument():
    assert resolve_path("/some/where.db") == "/some/where.db"


def test_resolve_path_falls_back_to_env(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "/from/env.db")
    assert resolve_path() == "/from/env.db"


def test_resolve_path_raises_when_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(RuntimeError):
        resolve_path()


def test_query_helpers(db):
    assert db.scalar("SELECT value_int FROM rules_constant WHERE id=?", "const-a") == 27
    assert db.one("SELECT * FROM rules_constant WHERE id=?", "const-a")["note"] == "a fake constant"
    assert db.q("SELECT * FROM rules_constant") != []
    assert db.scalar("SELECT value_int FROM rules_constant WHERE id=?", "missing") is None
    assert db.one("SELECT * FROM rules_constant WHERE id=?", "missing") is None


def test_handle_is_read_only(db):
    # the whole point of mode=ro: a consumer can never mutate the rulebook
    with pytest.raises(sqlite3.OperationalError):
        db.q("INSERT INTO rules_constant VALUES ('x', 1, 'nope')")


def test_context_manager_closes(rules_db_path):
    with RulesDB(rules_db_path) as handle:
        assert handle.scalar("SELECT COUNT(*) FROM rules_constant") == 1
    with pytest.raises(sqlite3.ProgrammingError):
        handle.q("SELECT 1")
