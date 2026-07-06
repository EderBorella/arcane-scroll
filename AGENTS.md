# AGENTS.md — Arcane Scroll

Hard-earned context for an agent working in this repo. Read `CLAUDE.md` first for the full working
rules; this file distills the operational gotchas you'd otherwise guess wrong.

## Commands

```bash
# Run the full suite (repo root)
.venv/bin/pytest -q

# Run a single test file
.venv/bin/pytest tests/validator/test_senses_check.py -v

# Run a single test
.venv/bin/pytest tests/validator/test_senses_check.py::test_resolver_max_not_sum -v
```

The venv lives at `.venv/`. Do NOT use plain `pytest` or `python -m pytest` — the venv isolate is
required (system Python lacks the packages).

## Architecture: the two layers

**Access layer** (`access/validator/*.py`) — pure DB-fact queries, no business rules. Modules mirror
the check domains: `identity.py`, `abilities.py`, `vitals.py`, `saving_throws.py`,
`proficiencies.py`, `feats.py`, `spellcasting.py`, `senses.py`.

**Validator checks** (`validator/checks/*.py`) — business rules, independently re-derived from DB facts.
Each exports `check(sheet: dict, access: ValidatorAccess) -> list[Violation]`. Register new checks
in `validator/checks/__init__.py` by importing the module and appending its `.check` to `ALL_CHECKS`.

**DO NOT put business-rule math in `access/`.** The access layer returns raw rows; the check derives
the rule from those rows.

## The test setup (critical)

Tests run against a **synthetic content-neutral DB** built in `tests/conftest.py::_build_rules_db()`.
It uses placeholder names: `class-a`, `Species A`, `feat-gen`, `sk1`, etc. — never real game terms.

- The validator tests use the `access` fixture (`tests/conftest.py:531`) — a `ValidatorAccess` wired
  to the synthetic DB.
- The access-layer tests use the `db` fixture (`tests/access/conftest.py:86`) — a raw `RulesDB`.
- **Test-file basenames must be unique** across `tests/` — no `__init__.py`, and pytest will collide
  on duplicate basenames. Disambiguate with a suffix.

When adding a new domain table, add its `CREATE TABLE` to the synthetic DB build AND the `_DIMS`
allow-list in `access/resolve.py` if the resolver should map its names.

## sqlite3.Row gotcha

`sqlite3.Row` objects use dict-style access (`row["column"]`) but **do NOT have `.get()`**. Use
`row["column"]` directly. Nullable int columns return `None`.

## Content neutrality (actions before every commit)

The repo must NEVER contain game proper nouns (species/class/subclass/feat/spell names), edition
identifiers, publisher acronyms, or the source dataset name. Before committing:
1. Inspect `git diff --staged` for any real game terms
2. Tests use synthetic placeholders only (`class-a`, `Species A`, `feat-gen`, `sk1`)
3. Commit messages describe structure, not content ("add subclass sense grants" not "add Species X
   darkvision")

## The reference DB

The compiled rulebook is at `/data/projects/arcane-scroll-data/reference-db/db/rules.db`. The app
reads it through the DAL; the env var `ARCANE_RULES_DB` points to it. The DB is built by an external
pipeline (`arcane-scroll-data/reference-db/scripts/`). Never edit `rules.db` by hand.

## Journal and board

The kanban board and feature cards live OUTSIDE the repo at `/data/projects/journal/arcane-scroll/`:
`board/{backlog,todo,in-progress,done}/` and `features/F05-*/`. The F05 README at
`features/F05-data-structure/README.md` is the task tracker for the current refactor. Every deferral
gets a board card immediately.

## Validator independence (the hardest rule)

The validator reads only the DB. **Never** set an expected value by looking at the generator's output,
and never tune a check so a known sheet passes. If the validator and generator disagree, the validator
(grounded in the DB) is assumed right until the DB source says otherwise. The generator is fixed last.

## Branch naming

Pattern: `feat/tNN-description` (e.g. `feat/t23-sense-resolution`). Branch off `main`.

## Gold harness — the mandatory re-test after every validator change

After ANY validator check change (new check, bugfix, logic update), run the gold corpus harness:

```bash
python3 /data/projects/arcane-scroll-data/gold-v7/harness.py
```

**How to read the output (the "golden method"):**

1. Every finding is a lead — it's either (a) a **validator bug**, (b) a **rules.DB data gap**, or
   (c) **real gold errata** (the sheet is wrong).
2. **Be skeptical of both sides.** Verify every finding against the reference dataset (at
   `/data/projects/arcane-scroll-data/reference-db/source/book.json` — local, uncommitted). Never assume the validator
   is right, and never assume the gold sheet is correct.
3. **Surface anything that requires a decision** — particularly discrepancies where:
   - The book rule is ambiguous and a ruling is needed
   - The validator is wrong and needs a code fix
   - The DB/validator doesn't yet cover the rule (missed edge case → new T-card)
   - A pattern of gold errata suggests the gold corpus is stale
4. **After finding gold errata**, fix the gold sheets (migrate to the next gold-corpus version,
   not in-place), then re-run the harness to confirm the findings are gone.
5. **Never suppress a finding to make numbers look better.** If the validator flags something and
   book-checking confirms the validator is correct, the sheet is wrong — don't soften the check.

The harness output shows `legal` (no ERROR/INTERNAL) and `complete` (no WARNING either). Aim for
100% on both; but pre-existing gold errata from OTHER domains (saving-throws, spellcasting, etc.)
are expected — never fix those by weakening the validator. Card them and move on.

## After finishing work: update the knowledge base and project state

Every completed piece of work should leave a trail. After a task lands (merged or branch ready for
review), do two things:

### 1. Update the knowledge base

If this work changed something durable — a new rule was modelled, a gotcha was discovered, a DB
table was added or changed, a build script was updated — add a note to the knowledge base:

```
/data/projects/journal/arcane-scroll/knowledge-base/V2/
```

- **`materialization-facts.md`** — updated table/row counts, new tables, schema changes
- **`reference-db-table-catalog.md`** — table/column documentation for new or changed tables
- **`build-pipeline-runbook.md`** — if the rebuild command or pipeline changed

For entirely new domains, create a new file following the existing naming convention.

### 2. Update PROJECT-STATE.md

Add a changelog entry to `docs/PROJECT-STATE.md` under the "Changelog (newest first)" section:

```
- **Short title (T-card ref).** What was done, why, and the key outcomes — numbers, new files,
  test counts. Keep to one paragraph. No proper nouns (no species/class/subclass/feat/spell names,
  no edition identifiers, no source file names). Describe structurally: "a subclass", "a species
  lineage", "a sense-grant extension flag".
```

Both files are **committed in the repo** — they must obey the same content-neutrality rules as
code. No game proper nouns, no source dataset names, no edition identifiers. Describe facts
structurally ("grant_sense table", "max-not-sum rule", "a subclass's permanent sense grant")
instead of naming the real content.
