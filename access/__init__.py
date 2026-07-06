"""Data-access layer over the compiled rulebook database (rules.db).

The reference book is a fully-typed relational SQLite DB built outside this repo; this package is the
*access machinery* that reads it — content-neutral (it knows table/column names, not game values) and
read-only. Layout:

    db          — the read-only connection handle + query helpers (RulesDB)
    primitives  — reusable retrieval primitives over the grant spine + common tables (DB facts only)
    validator   — the first per-consumer feature-access file (BOILERPLATE)

One feature-access file per consuming app; each composes the shared primitives into the specific
questions that app asks. Business-rule math stays in the feature files, never in primitives.
"""
