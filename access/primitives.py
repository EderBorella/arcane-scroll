"""Reusable retrieval primitives over the rulebook DB — pure DB facts, no business rules.

Everything the book *confers* lives on one uniform grant spine: a header row
(owner_kind, owner_id, gained_at_level, ...) in one of the grant_* tables, optionally with child
value rows keyed by grant_id. These primitives read that spine and a few common tables and return
raw rows. Business-rule math (proficiency-bonus formulas, spell-slot selection, skill totals) does
NOT belong here — it belongs in the per-consumer feature files, where it can be re-derived from the
rulebook rather than trusted from any existing consumer.

All queries are parameterised. The few places that interpolate an identifier (a table name) validate
it against a known set first — identifiers can't be bound as SQL parameters.
"""
from access.db import RulesDB

# The grant spine: each header table -> its child (value) tables, keyed by grant_id.
GRANT_TABLES: dict[str, list[str]] = {
    "grant_ability_increase": ["grant_ability_increase_value"],
    "grant_ability_set": [],
    "grant_bonus": [],
    "grant_companion": [],
    "grant_condition": [],
    "grant_d20_modifier": [],
    "grant_expertise": ["grant_expertise_value"],
    "grant_feat": [],
    "grant_hp": [],
    "grant_proficiency": ["grant_proficiency_value", "grant_proficiency_category",
                          "grant_proficiency_weapon_filter"],
    "grant_resistance": ["grant_resistance_option"],
    "grant_resource": [],
    "grant_save_advantage": [],
    "grant_sense": [],
    "grant_size": [],
    "grant_speed": [],
    "grant_spell": ["grant_spell_fixed", "grant_spell_choice", "grant_spell_choice_value"],
}


def grants_for(db: RulesDB, table: str, owner_kind: str, owner_id: str,
               at_level: int | None = None) -> list:
    """Header rows of ONE grant table for an owner. If at_level is given, keep only rows gained at or
    below it (a NULL gained_at_level means "always", so it is always included)."""
    if table not in GRANT_TABLES:
        raise ValueError(f"unknown grant table: {table!r}")
    sql = f"SELECT * FROM {table} WHERE owner_kind=? AND owner_id=?"
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    # Deterministic row order: every grant table has `id` as its primary key,
    # so ordering by it keeps grant rows stable across DB rebuilds (order only).
    sql += " ORDER BY id"
    return db.q(sql, *params)


# Cache of a child table's column list, so the deterministic ORDER BY is built
# once per table rather than re-introspected on every read.
_CHILD_COLS: dict[str, list[str]] = {}


def _child_columns(db: RulesDB, table: str) -> list[str]:
    """Column names of a grant child table (from the schema), cached. Used to build a
    fully deterministic ORDER BY — child tables have no single `id` PK like the header
    tables, so ordering over every column is the stable, always-present key."""
    cols = _CHILD_COLS.get(table)
    if cols is None:
        # `table` is validated against GRANT_TABLES by the caller; PRAGMA cannot bind params.
        cols = [r["name"] for r in db.q(f"PRAGMA table_info({table})")]
        _CHILD_COLS[table] = cols
    return cols


def children_of(db: RulesDB, header_table: str, grant_id: str) -> dict[str, list]:
    """The child value rows of one grant header row, grouped by child table name.
    Rows are ordered deterministically (by every column) so child-row order is stable
    across DB rebuilds — order only, no value change."""
    if header_table not in GRANT_TABLES:
        raise ValueError(f"unknown grant table: {header_table!r}")
    out = {}
    for child in GRANT_TABLES[header_table]:
        order_by = ", ".join(_child_columns(db, child))
        sql = f"SELECT * FROM {child} WHERE grant_id=?"
        if order_by:
            sql += f" ORDER BY {order_by}"
        out[child] = db.q(sql, grant_id)
    return out


def all_grants_for(db: RulesDB, owner_kind: str, owner_id: str,
                   at_level: int | None = None) -> dict[str, list]:
    """Everything a source confers: {grant_table: [header rows]} across the whole spine, non-empty
    tables only. The highest-value primitive — "give me everything this owner grants"."""
    out = {}
    for table in GRANT_TABLES:
        rows = grants_for(db, table, owner_kind, owner_id, at_level)
        if rows:
            out[table] = rows
    return out


def resource_at(db: RulesDB, resource_id: str, level: int):
    """The class-resource ladder row at the highest tracked level <= `level` (or None)."""
    return db.one(
        "SELECT * FROM class_resource_level WHERE resource_id=? AND level<=? ORDER BY level DESC LIMIT 1",
        resource_id, level)


def features_at(db: RulesDB, class_id: str | None = None, subclass_id: str | None = None,
                level: int | None = None) -> list:
    """Class or subclass feature rows granted at or below a level (ordered by level)."""
    if class_id:
        sql, params, lvl = "SELECT * FROM class_feature WHERE class_id=?", [class_id], "level"
    elif subclass_id:
        sql, params, lvl = "SELECT * FROM subclass_feature WHERE subclass_id=?", [subclass_id], "class_level"
    else:
        raise ValueError("features_at needs class_id or subclass_id")
    if level is not None:
        sql += f" AND {lvl}<=?"
        params.append(level)
    return db.q(sql + f" ORDER BY {lvl}", *params)


def sum_bonuses(db: RulesDB, owner_kind: str, owner_id: str, target_kind: str,
                target_id: str | None = None) -> int:
    """Sum of grant_bonus.value for an owner toward a target (flat numeric bonuses only). Note the
    same-name-no-stack rule is a CONSUMER concern — this just totals the rows it is given."""
    sql = ("SELECT COALESCE(SUM(value),0) FROM grant_bonus "
           "WHERE owner_kind=? AND owner_id=? AND target_kind=?")
    params = [owner_kind, owner_id, target_kind]
    if target_id is not None:
        sql += " AND target_id=?"
        params.append(target_id)
    return db.scalar(sql, *params)


def constant(db: RulesDB, const_id: str):
    """A rulebook constant's integer value (rules_constant.value_int), or None."""
    return db.scalar("SELECT value_int FROM rules_constant WHERE id=?", const_id)


# Tables `exists()` may probe — kept small and explicit so the interpolated identifier is never
# caller-controlled SQL.
_EXISTS_TABLES = {"class_feature", "subclass_feature", "class_resource", "detail_option",
                  "spell", "feat", "magic_item", "creature"}


def exists(db: RulesDB, table: str, id_value: str, id_col: str = "id") -> bool:
    """True if a row with the given id exists in an allow-listed table (referential sanity checks)."""
    if table not in _EXISTS_TABLES:
        raise ValueError(f"exists() not allowed for table {table!r}")
    return db.one(f"SELECT 1 FROM {table} WHERE {id_col}=?", id_value) is not None


def item_grants_for(db: RulesDB, sheet: dict, grant_table: str,
                    resolver) -> list:
    """Grant rows of one table for every magic item the character has equipped or in backpack.
    Resolves item names by direct catalog_item.name lookup (bypasses the resolver's parenthetical
    stripping, which would collapse 'Ioun Stone (Protection)' and 'Ioun Stone (Sustenance)')."""
    rows = []
    if grant_table not in GRANT_TABLES:
        raise ValueError(f"unknown grant table: {grant_table!r}")

    seen_items = set()
    items = []
    equipped = sheet.get("equipped")
    if isinstance(equipped, dict):
        items.extend(equipped.values())
    backpack = sheet.get("backpack")
    if isinstance(backpack, list):
        items.extend(backpack)

    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("magic") is not True:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        # Direct catalog_item lookup (case-insensitive) to avoid _norm collisions
        item_id = db.scalar(
            "SELECT mi.id FROM magic_item mi "
            "JOIN catalog_item ci ON mi.id = ci.id "
            "WHERE LOWER(ci.name) = ?", name.strip().lower())
        if not item_id:
            continue
        # Attunement check: if item requires attunement, it must be attuned
        requires = db.scalar(
            "SELECT requires_attunement FROM magic_item WHERE id=?", item_id)
        if requires:
            attune = item.get("attunement")
            if not isinstance(attune, dict) or attune.get("attuned") is not True:
                continue
        if item_id not in seen_items:
            seen_items.add(item_id)
            gr = grants_for(db, grant_table, "magic_item", item_id)
            rows.extend(gr)
    return rows
