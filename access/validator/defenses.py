"""Defenses-domain DB facts: resistance, condition immunity, and save-advantage grants."""
from access.validator import ValidatorAccess


def gather_owner_grants(access: ValidatorAccess, sheet: dict, query_fn) -> list:
    """Collect all grant rows for every character owner using ``query_fn(access, kind, id, level?)``.

    A shared retrieval walker (no rule math): both the derivation engine and the defenses check read
    the same owner set from the DB via the supplied per-grant query, then each derives the resulting
    defence set independently (T78/T96)."""
    rows: list = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")

    spid = access.resolve("species", species_name)
    if spid:
        rows.extend(query_fn(access, "species", spid))

    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            rows.extend(query_fn(access, "lineage", lid))
            parent_spid = access.db.scalar(
                "SELECT species_id FROM lineage WHERE id=?", lid)
            if parent_spid and parent_spid != spid:
                rows.extend(query_fn(access, "species", parent_spid))

    raw_classes = ident.get("classes")
    if isinstance(raw_classes, list):
        for c in raw_classes:
            if not isinstance(c, dict):
                continue
            level = c.get("level")
            if not isinstance(level, int) or isinstance(level, bool):
                continue
            cid = access.resolve("class", c.get("class"))
            if cid is None:
                continue
            rows.extend(query_fn(access, "class", cid, level))
            sub = c.get("subclass")
            if sub:
                sid = access.resolve("subclass", sub)
                if sid:
                    rows.extend(query_fn(access, "subclass", sid, level))

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = access.resolve("feat", f.get("name"))
            if fid:
                rows.extend(query_fn(access, "feat", fid))

    return rows


def resistance_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                      at_level: int | None = None) -> list:
    """Raw grant_resistance rows for an owner, optionally level-gated."""
    sql = ("SELECT id, damage_type_id, mode, choose_n, variant_axis, source_filter "
           "FROM grant_resistance WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def state_resistance_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list:
    """Condition-gated (state-active-only) fixed grant_resistance rows for an owner.

    These carry a non-NULL ``condition_kind`` marker: they materialise only while
    the owning state is active, which is why the CORE permanent-defenses gatherer
    (which walks always-on owners) does not pick them up."""
    return access.db.q(
        "SELECT id, damage_type_id, mode, condition_kind FROM grant_resistance "
        "WHERE owner_kind=? AND owner_id=? AND condition_kind IS NOT NULL "
        "AND mode='fixed' AND damage_type_id IS NOT NULL",
        owner_kind, owner_id)


def condition_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                     at_level: int | None = None) -> list:
    """Raw grant_condition rows for an owner, optionally level-gated."""
    sql = ("SELECT id, condition_id, effect "
           "FROM grant_condition WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def save_advantage_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                          at_level: int | None = None) -> list:
    """Raw grant_save_advantage rows for an owner, optionally level-gated."""
    sql = ("SELECT id, scope_kind, ability_id, note "
           "FROM grant_save_advantage WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def check_advantage_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                           at_level: int | None = None) -> list:
    """Raw always-on ability-check advantage grants for an owner, optionally level-gated.

    Reads ``grant_d20_modifier`` rows scoped to an ability check (``target_kind='check'``) that
    confer advantage (``modifier_id='advantage'``). Each row carries one structured ``scope`` (an
    owner may confer several — one row per scope, mirroring the ``grant_save_advantage`` spine). Pure
    DB read — the scope mapping lives in ``check_scope_for`` and the accumulation in the consumer, so
    the deriver and the check each re-derive the resulting set independently."""
    sql = ("SELECT id, target_kind, ability_id, modifier_id, scope "
           "FROM grant_d20_modifier "
           "WHERE owner_kind=? AND owner_id=? AND target_kind='check' AND modifier_id='advantage'")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def check_scope_for(access: ValidatorAccess, row: dict) -> str | None:
    """Map a ``grant_d20_modifier`` check-advantage row to its check_advantages scope string.

    The scope is read from the row's STRUCTURED ``scope`` column (one row per scope), not hardcoded:
    an owner that confers advantage on several checks (e.g. the initiative roll AND a skill check)
    carries one row per scope, each with the ability that governs that check (Initiative → Dexterity,
    Athletics → Strength, Perception → Wisdom). Because the scope is data-driven and the ability is
    per-row, a non-Dexterity check advantage is never mislabelled as ``initiative``. The free-text
    ``scope_note`` stays render-only."""
    if row["modifier_id"] == "advantage" and row["target_kind"] == "check":
        return row["scope"]
    return None


def resistance_options(access: ValidatorAccess, grant_id: str) -> list[str]:
    """Damage-type option pool for a choose-mode resistance grant."""
    return [r["damage_type_id"]
            for r in access.db.q("SELECT damage_type_id FROM grant_resistance_option WHERE grant_id=?", grant_id)]


def damage_type_ids(access: ValidatorAccess) -> list[str]:
    """All known damage type IDs."""
    return [r["id"] for r in access.db.q("SELECT id FROM damage_type")]


def condition_ids(access: ValidatorAccess) -> list[str]:
    """All known condition ids."""
    return [r["id"] for r in access.db.q("SELECT id FROM condition")]


def ac_formulas(access: ValidatorAccess, owner_kind: str, owner_id: str,
                at_level: int | None = None) -> list[dict]:
    """Alternative Armor-Class formulas an owner confers, each bundled with the ability ids the
    formula sums. Returns ``[{id, owner_kind, owner_id, base, allows_shield, gained_at_level,
    ability_ids}, ...]``.

    ``owner_kind`` is 'base' (the universal ``unarmored`` default), 'class', or 'subclass';
    ``allows_shield`` is a bool (a formula that does not permit a Shield's AC bonus while in use);
    ``ability_ids`` are the canonical DB ability ids added to ``base``. If ``at_level`` is given, only
    formulas gained at or below it are included (a NULL gained_at_level always applies) — the same
    level gating the other grant queries use.

    Pure DB read — the per-formula arithmetic (base + ability mods + optional shield) and the
    most-beneficial pick across several applicable formulas live in the consumer (deriver and check
    each re-derive it independently)."""
    sql = ("SELECT id, base, allows_shield, gained_at_level FROM ac_formula "
           "WHERE owner_kind=? AND owner_id=?")
    params: list = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    out: list[dict] = []
    for r in access.db.q(sql, *params):
        ability_ids = [a["ability_id"] for a in access.db.q(
            "SELECT ability_id FROM ac_formula_ability WHERE formula_id=?", r["id"])]
        out.append({
            "id": r["id"],
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "base": r["base"],
            "allows_shield": bool(r["allows_shield"]),
            "gained_at_level": r["gained_at_level"],
            "ability_ids": ability_ids,
        })
    return out


def ac_bonus_grants(access: ValidatorAccess, owner_kind: str, owner_id: str) -> list[int]:
    """Flat Armor-Class bonus values an owner grants (``grant_bonus`` with ``target_kind='ac'``).
    Pure DB read — the stacking (a plain sum) lives in the consumer."""
    return [r["value"] for r in access.db.q(
        "SELECT value FROM grant_bonus WHERE owner_kind=? AND owner_id=? AND target_kind='ac'",
        owner_kind, owner_id) if r["value"]]


def variant_damage_type(access: ValidatorAccess, species_id: str, axis: str,
                        option_name: str) -> str | None:
    """Resolve a species_variant choice to its damage_type_id, e.g.
    a species + an ancestry-choice axis + variant-a -> a damage type."""
    return access.db.scalar(
        "SELECT damage_type_id FROM species_variant_option "
        "WHERE species_id=? AND axis=? AND option_name=?",
        species_id, axis, option_name)


def save_scope_for(access: ValidatorAccess, row: dict) -> str | None:
    """Map a grant_save_advantage row to a save_advantages scope string.
    ability scope -> ability abbreviation. concentration/death_save/spells -> keyword."""
    if row["scope_kind"] == "ability":
        abbr = access.db.scalar("SELECT abbrev FROM ability WHERE id=?", row["ability_id"])
        return abbr
    if row["scope_kind"] == "concentration":
        return "concentration"
    if row["scope_kind"] == "death_save":
        return "death"
    if row["scope_kind"] == "spells":
        return "spells"
    return None
