"""Vitals domain: hit-dice pool (face + count per class) and HP-range consistency (con modifier +
class hit dice + species HP riders). Every expectation is derived from the DB; malformed or missing
sheet data is skipped rather than raised."""
from access.validator import abilities as abilities_q
from access.validator import vitals as q
from validator.report import Violation

DOMAIN = "vitals"

# The real-DB abbrev for the constitution ability (per contract v6, sheet ability keys are
# abbreviations: str/dex/con/int/wis/cha).
CON_ABBREV = "con"


def _resolved_classes(classes, access) -> list[tuple[str, int, int]]:
    """[(class_id, level, hit_die_faces), ...] for the classes that resolve cleanly; malformed or
    unknown entries are skipped rather than raised."""
    out = []
    for c in classes:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not isinstance(level, int) or isinstance(level, bool):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        faces = q.class_hit_die(access, cid)
        if faces is None:
            continue
        out.append((cid, level, faces))
    return out


def _con_modifier(abilities_sheet, access) -> int | None:
    if not isinstance(abilities_sheet, dict):
        return None
    con_id = abilities_q.ability_id(access, CON_ABBREV)
    if con_id is None:
        return None
    for k, entry in abilities_sheet.items():
        if not isinstance(entry, dict) or abilities_q.ability_id(access, k) != con_id:
            continue
        final = entry.get("final")
        if isinstance(final, int) and not isinstance(final, bool):
            return (final - 10) // 2
    return None


def _vitals_location(sheet: dict) -> tuple[object, object, str]:
    """Locate the hit-points and hit-dice sub-objects plus the report-path prefix for them. A
    combat-nested sheet keeps both under a `combat` object; a top-level-fields sheet keeps them at
    the document root. Branch on the shape rather than hard-switching so both are supported."""
    combat = sheet.get("combat")
    if isinstance(combat, dict):
        return combat.get("hit_points"), combat.get("hit_dice"), "combat."
    return sheet.get("hit_points"), sheet.get("hit_dice"), ""


def _check_hit_dice_pool(v: list[Violation], hit_dice, resolved: list[tuple[str, int, int]],
                         total_level: int, prefix: str) -> None:
    if not isinstance(hit_dice, dict):
        return
    expected_pool: dict[str, int] = {}
    for _, lvl, faces in resolved:
        key = f"d{faces}"
        expected_pool[key] = expected_pool.get(key, 0) + lvl

    actual_total = 0
    for key, entry in hit_dice.items():
        if not isinstance(entry, dict):
            continue
        maxv = entry.get("max")
        if not isinstance(maxv, int) or isinstance(maxv, bool):
            continue
        actual_total += maxv
        if key not in expected_pool:
            v.append(Violation(DOMAIN, "hit-dice-face-invalid", "illegal",
                               f"unexpected hit-die face {key!r} for this class combination",
                               f"{prefix}hit_dice.{key}"))
        elif maxv != expected_pool[key]:
            v.append(Violation(DOMAIN, "hit-dice-count-mismatch", "illegal",
                               f"{key}: max {maxv} != expected {expected_pool[key]}",
                               f"{prefix}hit_dice.{key}"))

    if actual_total != total_level:
        v.append(Violation(DOMAIN, "hit-dice-total-mismatch", "illegal",
                           f"hit dice total {actual_total} != total level {total_level}",
                           f"{prefix}hit_dice"))


def _check_hp_range(v: list[Violation], hp, access, sheet: dict, resolved: list[tuple[str, int, int]],
                    total_level: int, con_mod: int | None, prefix: str) -> None:
    if con_mod is None or not resolved:
        return
    actual_max = hp.get("max") if isinstance(hp, dict) else None
    if not isinstance(actual_max, int) or isinstance(actual_max, bool):
        return

    _, _, first_faces = resolved[0]
    hp_min = first_faces + con_mod + (total_level - 1) * max(1, 1 + con_mod)
    hp_max = sum(lvl * (faces + con_mod) for _, lvl, faces in resolved)

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    species_id = access.resolve("species", ident.get("species"))
    if species_id is not None:
        for row in q.hp_grants(access, "species", species_id):
            hp_max += (row["flat"] or 0) + (row["per_level"] or 0) * total_level

    if not (hp_min <= actual_max <= hp_max):
        v.append(Violation(DOMAIN, "hp-out-of-range", "illegal",
                           f"hit points max {actual_max} outside the expected range [{hp_min}, {hp_max}]",
                           f"{prefix}hit_points.max"))


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    raw_classes = ident.get("classes")
    if not isinstance(raw_classes, list) or not raw_classes:
        return v

    resolved = _resolved_classes(raw_classes, access)
    if not resolved:
        return v
    total_level = sum(lvl for _, lvl, _ in resolved)

    hp, hit_dice, prefix = _vitals_location(sheet)
    _check_hit_dice_pool(v, hit_dice, resolved, total_level, prefix)

    con_mod = _con_modifier(sheet.get("abilities"), access)
    _check_hp_range(v, hp, access, sheet, resolved, total_level, con_mod, prefix)
    return v
