"""Regression: the child-column introspection cache must be keyed by DB handle,
not by table name alone. Two handles whose same-named child table has a different
column set must each get their OWN columns — a handle must never be served another
handle's cached columns (which would build an ORDER BY over a missing column)."""
import sqlite3

from access import primitives as p
from access.db import RulesDB


def _build_child_only(path: str, extra_cols: str) -> None:
    """A minimal DB carrying a single grant child table with a caller-chosen column set."""
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE grant_spell_fixed (grant_id TEXT, {extra_cols})")
    con.commit()
    con.close()


def test_child_cols_cache_is_per_handle(tmp_path):
    db1_path = tmp_path / "one.db"
    db2_path = tmp_path / "two.db"
    _build_child_only(str(db1_path), "spell_id TEXT")
    _build_child_only(str(db2_path), "spell_id TEXT, extra_col TEXT")

    with RulesDB(str(db1_path)) as db1, RulesDB(str(db2_path)) as db2:
        # Prime the cache from the first handle, then read the second handle whose
        # same-named table has an extra column. Under a table-name-only key the
        # second read would wrongly return the first handle's stale columns.
        assert p._child_columns(db1, "grant_spell_fixed") == ["grant_id", "spell_id"]
        assert p._child_columns(db2, "grant_spell_fixed") == [
            "grant_id", "spell_id", "extra_col"]
