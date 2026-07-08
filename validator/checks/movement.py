"""Movement domain: speed resolution for walk, fly, swim, climb, burrow modes from the grant_speed
spine. Rules: sets_total takes MAX (overrides), additive SUMs on top, equals_walk mirrors resolved
walk speed, and class_resource bonuses add to walk."""
from access.validator import movement as q
from validator.report import Violation

DOMAIN = "movement"


def _resolve_speeds(grant_rows: list, base_walk: int, class_bonuses: list[int]) -> dict[str, int]:
    phases = {"walk": base_walk or 0}
    sets_total_max: dict[str, int] = {}
    additive_sum: dict[str, int] = {}
    equals_walk_modes: set[str] = set()

    for row in grant_rows:
        mode = row["movement_mode_id"]
        if row["sets_total"]:
            ft = row["feet"]
            if ft is not None:
                sets_total_max[mode] = max(sets_total_max.get(mode, 0), ft)
        elif row["additive"]:
            additive_sum[mode] = additive_sum.get(mode, 0) + (row["feet"] or 0)
        elif row["equals_walk"]:
            equals_walk_modes.add(mode)

    for mode, ft in sets_total_max.items():
        phases[mode] = ft

    for mode, ft in additive_sum.items():
        phases[mode] = phases.get(mode, 0) + ft

    if class_bonuses:
        phases["walk"] = phases.get("walk", 0) + max(class_bonuses)

    for mode in equals_walk_modes:
        if mode != "walk":
            phases[mode] = phases.get("walk", 0)

    return {k: v for k, v in phases.items() if v > 0}


def _gather_owner_grants(access, sheet: dict) -> list:
    rows: list = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")

    spid = access.resolve("species", species_name)
    if spid:
        rows.extend(q.speed_grants(access, "species", spid))

    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            rows.extend(q.speed_grants(access, "lineage", lid))
            parent_spid = q.lineage_parent_species(access, lid)
            if parent_spid and parent_spid != spid:
                rows.extend(q.speed_grants(access, "species", parent_spid))

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
            rows.extend(q.speed_grants(access, "class", cid, level))
            sub = c.get("subclass")
            if sub:
                sid = access.resolve("subclass", sub)
                if sid:
                    rows.extend(q.speed_grants(access, "subclass", sid, level))

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = access.resolve("feat", f.get("name"))
            if fid:
                rows.extend(q.speed_grants(access, "feat", fid))

    # magic items
    from access import primitives
    rows.extend(primitives.item_grants_for(access.db, sheet, "grant_speed", access.resolver))

    return rows


def _gather_class_bonuses(access, sheet: dict) -> list[int]:
    bonuses: list[int] = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

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
            bonus = q.class_speed_bonus(access, cid, level)
            if bonus is not None:
                bonuses.append(bonus)

    return bonuses


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")
    spid = access.resolve("species", species_name)
    base_walk = q.species_base_walk(access, spid) if spid else 0

    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            parent_spid = q.lineage_parent_species(access, lid)
            if parent_spid and not base_walk:
                base_walk = q.species_base_walk(access, parent_spid) or base_walk

    grant_rows = _gather_owner_grants(access, sheet)
    class_bonuses = _gather_class_bonuses(access, sheet)

    expected = _resolve_speeds(grant_rows, base_walk, class_bonuses)

    combat = sheet.get("combat")
    if not isinstance(combat, dict):
        combat = {}
    sheet_speed = combat.get("speed")
    if not isinstance(sheet_speed, dict):
        sheet_speed = {}

    known_ids = set(q.movement_mode_ids(access))

    for mode_id, expected_speed in expected.items():
        actual = sheet_speed.get(mode_id)
        if actual is None:
            v.append(Violation(DOMAIN, "movement-missing", "incomplete",
                               f"expected {mode_id} {expected_speed}ft, not on sheet",
                               f"combat.speed.{mode_id}"))
        elif not isinstance(actual, int) or isinstance(actual, bool):
            v.append(Violation(DOMAIN, "movement-speed-mismatch", "illegal",
                               f"{mode_id}: expected {expected_speed}ft, got {actual!r}",
                               f"combat.speed.{mode_id}"))
        elif actual != expected_speed:
            v.append(Violation(DOMAIN, "movement-speed-mismatch", "illegal",
                               f"{mode_id}: expected {expected_speed}ft, got {actual}ft",
                               f"combat.speed.{mode_id}"))

    for mode_id, actual in sheet_speed.items():
        if mode_id not in expected and mode_id in known_ids:
            if isinstance(actual, int) and not isinstance(actual, bool):
                v.append(Violation(DOMAIN, "movement-ungranted", "illegal",
                                   f"{mode_id} {actual}ft: no grant found for this mode",
                                   f"combat.speed.{mode_id}"))

    return v
