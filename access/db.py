"""Read-only connection handle over the compiled rulebook database (rules.db).

Content-neutral machinery: this module knows table/column NAMES but holds no game data — the values
live in the local store, addressed by id. The DB path comes from the environment (ARCANE_RULES_DB)
or an explicit argument; nothing is hard-coded to a host path. The connection is opened READ-ONLY so
a consumer can never mutate the rulebook.
"""
import os
import sqlite3

ENV_VAR = "ARCANE_RULES_DB"


def resolve_path(path: str | None = None) -> str:
    """The rules DB path from the argument, else $ARCANE_RULES_DB. Raises if neither is set."""
    p = path or os.environ.get(ENV_VAR)
    if not p:
        raise RuntimeError(f"rules DB path not set: pass path= or set ${ENV_VAR}")
    return p


class RulesDB:
    """A read-only handle over rules.db with small query helpers.

        q(sql, *params)      -> list[Row]     all rows
        one(sql, *params)    -> Row | None    first row
        scalar(sql, *params) -> value | None  first column of first row

    Rows are sqlite3.Row (index- and name-addressable). Use as a context manager, or call close()."""

    def __init__(self, path: str | None = None):
        self.path = resolve_path(path)
        # mode=ro (URI) makes the whole handle read-only — reads only, no accidental writes.
        self._con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._con.row_factory = sqlite3.Row

    def q(self, sql: str, *params) -> list[sqlite3.Row]:
        return self._con.execute(sql, params).fetchall()

    def one(self, sql: str, *params) -> sqlite3.Row | None:
        return self._con.execute(sql, params).fetchone()

    def scalar(self, sql: str, *params):
        row = self._con.execute(sql, params).fetchone()
        return row[0] if row is not None else None

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "RulesDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
