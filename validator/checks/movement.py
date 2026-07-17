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

    # Iterate in a stable order so the resulting speed-dict key order is
    # deterministic (a raw set iterates in hash-seed-dependent order across
    # processes). Order only — the values written are unchanged.
    for mode in sorted(equals_walk_modes):
        if mode != "walk":
            phases[mode] = phases.get("walk", 0)

    return {k: v for k, v in phases.items() if v > 0}


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

    grant_rows = q.gather_owner_grants(access, sheet)
    class_bonuses = q.gather_class_bonuses(access, sheet)

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
