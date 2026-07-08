"""Defenses domain: damage resistances, damage immunities, condition immunities, and save-advantage
grants. The sheet's ``defenses`` object carries three arrays the check validates:

* ``resistances`` — damage types the character resists (from fixed-mode ``grant_resistance`` rows)
* ``immunities`` — damage types the character is immune to (no DB source currently)
* ``condition_immunities`` — conditions the character is immune to (from ``grant_condition`` rows)
"""
from access.validator import defenses as q
from validator.report import Violation

DOMAIN = "defenses"


def _gather_owner_grants(access, sheet: dict, query_fn):
    """Collect all grant rows for every character owner using *query_fn(access, kind, id, level?)."""
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


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    resistance_rows = _gather_owner_grants(access, sheet, q.resistance_grants)

    # magic items: resistance grants
    from access import primitives
    resistance_rows.extend(
        primitives.item_grants_for(access.db, sheet, "grant_resistance", access.resolver))

    expected_resistances: set[str] = set()
    for row in resistance_rows:
        if row["mode"] == "fixed" and row["damage_type_id"]:
            expected_resistances.add(row["damage_type_id"])

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    variant_name = ident.get("species_variant")
    if variant_name and isinstance(variant_name, str):
        spid = access.resolve("species", ident.get("species"))
        if spid:
            for row in resistance_rows:
                if row["variant_axis"]:
                    dmg = q.variant_damage_type(access, spid, row["variant_axis"], variant_name)
                    if dmg:
                        expected_resistances.add(dmg)

    condition_rows = _gather_owner_grants(access, sheet, q.condition_grants)
    condition_rows.extend(
        primitives.item_grants_for(access.db, sheet, "grant_condition", access.resolver))
    expected_condition_immunities: set[str] = set()
    for row in condition_rows:
        if row["effect"] == "immunity":
            expected_condition_immunities.add(row["condition_id"])

    defenses = sheet.get("defenses")
    if not isinstance(defenses, dict):
        defenses = {}

    sheet_resistances = defenses.get("resistances")
    if not isinstance(sheet_resistances, list):
        sheet_resistances = []
    sheet_immunities = defenses.get("immunities")
    if not isinstance(sheet_immunities, list):
        sheet_immunities = []
    sheet_condition_immunities = defenses.get("condition_immunities")
    if not isinstance(sheet_condition_immunities, list):
        sheet_condition_immunities = []

    sheet_res_set = set(sheet_resistances)
    sheet_imm_set = set(sheet_immunities)
    sheet_cond_set = set(sheet_condition_immunities)

    known_damage = set(q.damage_type_ids(access))
    known_conditions = set(q.condition_ids(access))

    for dt in expected_resistances:
        if dt not in sheet_res_set:
            v.append(Violation(DOMAIN, "resistance-missing", "incomplete",
                               f"expected resistance to {dt}, not on sheet",
                               "defenses.resistances"))

    for dt in sheet_res_set:
        if dt not in expected_resistances:
            if dt in known_damage:
                v.append(Violation(DOMAIN, "resistance-ungranted", "illegal",
                                   f"resistance to {dt}: no grant found",
                                   "defenses.resistances"))

    for dt in sheet_imm_set:
        if dt in known_damage:
            v.append(Violation(DOMAIN, "immunity-ungranted", "illegal",
                               f"immunity to {dt}: no grant found",
                               "defenses.immunities"))

    for cid in expected_condition_immunities:
        if cid not in sheet_cond_set:
            v.append(Violation(DOMAIN, "condition-immunity-missing", "incomplete",
                               f"expected immunity to {cid}, not on sheet",
                               "defenses.condition_immunities"))

    for cid in sheet_cond_set:
        if cid not in expected_condition_immunities:
            if cid in known_conditions:
                v.append(Violation(DOMAIN, "condition-immunity-ungranted", "illegal",
                                   f"immunity to {cid}: no grant found",
                                   "defenses.condition_immunities"))

    # save advantages
    sa_rows = _gather_owner_grants(access, sheet, q.save_advantage_grants)
    sa_rows.extend(
        primitives.item_grants_for(access.db, sheet, "grant_save_advantage", access.resolver))
    expected_sa: set[str] = set()
    for row in sa_rows:
        scope = q.save_scope_for(access, row)
        if scope:
            expected_sa.add(scope)

    sheet_sa = defenses.get("save_advantages")
    if not isinstance(sheet_sa, list):
        sheet_sa = []
    sheet_sa_set = set(sheet_sa)

    for scope in expected_sa:
        if scope not in sheet_sa_set:
            v.append(Violation(DOMAIN, "save-advantage-missing", "incomplete",
                               f"expected save advantage '{scope}', not on sheet",
                               "defenses.save_advantages"))

    for scope in sheet_sa_set:
        if scope not in expected_sa:
            v.append(Violation(DOMAIN, "save-advantage-ungranted", "illegal",
                               f"save advantage '{scope}': no grant found",
                               "defenses.save_advantages"))

    # condition advantages (from grant_condition with advantage effects)
    expected_ca: dict[str, str] = {}  # condition_id -> effect
    for row in condition_rows:
        if row["effect"] in ("advantage_to_avoid_or_end", "advantage_to_end"):
            key = row["condition_id"]
            effect = "avoid_or_end" if row["effect"] == "advantage_to_avoid_or_end" else "end"
            expected_ca[key] = effect

    sheet_ca = defenses.get("condition_advantages")
    if not isinstance(sheet_ca, list):
        sheet_ca = []
    sheet_ca_map: dict[str, str] = {}
    for entry in sheet_ca:
        if isinstance(entry, dict):
            c = entry.get("condition")
            e = entry.get("effect")
            if c and e:
                sheet_ca_map[c] = e

    for cond, effect in expected_ca.items():
        if cond not in sheet_ca_map:
            v.append(Violation(DOMAIN, "condition-advantage-missing", "incomplete",
                               f"expected condition advantage vs {cond}, not on sheet",
                               "defenses.condition_advantages"))
        elif sheet_ca_map[cond] != effect:
            v.append(Violation(DOMAIN, "condition-advantage-effect-mismatch", "illegal",
                               f"condition advantage vs {cond}: expected '{effect}', got '{sheet_ca_map[cond]}'",
                               "defenses.condition_advantages"))

    for cond in sheet_ca_map:
        if cond not in expected_ca:
            if cond in known_conditions:
                v.append(Violation(DOMAIN, "condition-advantage-ungranted", "illegal",
                                   f"condition advantage vs {cond}: no grant found",
                                   "defenses.condition_advantages"))

    return v
