# `access/` — rulebook data-access layer

Read-only access to the compiled reference rulebook (`rules.db`, built outside this repo). Replaces
the old regex `build_rules.py` + flat-file approach: consumers query the typed relational DB instead
of loading mined JSON.

## Layout
- **`db.py`** — `RulesDB`, a read-only connection handle. Path from `$ARCANE_RULES_DB` (or an explicit
  `path=`); opened `mode=ro` so no consumer can mutate the rulebook. Helpers: `q` / `one` / `scalar`.
- **`primitives.py`** — reusable retrieval primitives over the grant spine + common tables. **DB facts
  only**, fully parameterised. The grant spine is uniform: a header row
  `(owner_kind, owner_id, gained_at_level, …)` in a `grant_*` table, with optional child value rows
  keyed by `grant_id`. `all_grants_for()` is the workhorse: "everything this source confers."
- **`validator.py`** — the first *feature-access file* (currently **boilerplate**). One per consuming
  app; composes primitives into that app's specific questions.

## Conventions
1. **Read-only.** Always go through `RulesDB` (mode=ro). The DB is authored by the build pipeline; no
   consumer writes it.
2. **Parameterise everything.** Never interpolate a value into SQL. The only interpolated identifiers
   are table names, and those are validated against an allow-list first.
3. **One feature-access file per app** (`validator.py`, later `generator.py`, …). Raw SQL lives in
   `primitives`; how-to-compose lives in the feature file.
4. **No business rules in `primitives`.** Proficiency-bonus math, spell-slot selection, totals, etc.
   live in the feature files, freshly derived from the rulebook — never copied from an existing
   consumer (which may be wrong).
5. **Content-neutral.** This code knows table/column names only; game data values live in `rules.db`.
   Tests build a synthetic DB (fake vocabulary) so they carry no content and run anywhere.

## Configuration
- `ARCANE_RULES_DB` — path to `rules.db`. No default host path is baked in.

## Tests
`tests/access/` — `conftest.py` builds a synthetic DB with the real table shapes; run with `pytest`.
