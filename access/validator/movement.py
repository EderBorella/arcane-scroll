"""Movement-domain DB facts: grant_speed rows, species base walk speed, movement modes, and class speed bonuses."""
from access.validator import ValidatorAccess


def speed_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                 at_level: int | None = None) -> list:
    """Raw grant_speed rows for an owner, optionally level-gated."""
    sql = ("SELECT movement_mode_id, feet, equals_walk, sets_total, additive "
           "FROM grant_speed WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def species_base_walk(access: ValidatorAccess, species_id: str) -> int | None:
    """The base walk speed for a species (base_walk_speed column)."""
    return access.db.scalar("SELECT base_walk_speed FROM species WHERE id=?", species_id)


def lineage_parent_species(access: ValidatorAccess, lineage_id: str) -> str | None:
    """The species id a lineage belongs to, or None if unknown."""
    return access.db.scalar("SELECT species_id FROM lineage WHERE id=?", lineage_id)


def movement_mode_ids(access: ValidatorAccess) -> list[str]:
    """All known movement mode ids."""
    return [r["id"] for r in access.db.q("SELECT id FROM movement_mode")]


def class_speed_bonus(access: ValidatorAccess, class_id: str, level: int) -> int | None:
    """Highest bonus from class_resource_level at or below the given level for a speed-related
    class resource (e.g. Unarmored Movement). Only resources whose name includes 'movement'
    or 'speed' are considered — other class_resource.bonus columns (like a damage-boost resource) are
    not speed bonuses."""
    return access.db.scalar(
        "SELECT MAX(crl.bonus) FROM class_resource_level crl "
        "JOIN class_resource cr ON cr.id=crl.resource_id "
        "WHERE cr.owner_kind='class' AND cr.owner_id=? AND crl.level<=? AND crl.bonus IS NOT NULL "
        "AND (cr.name LIKE '%movement%' OR cr.name LIKE '%Movement%' "
        "     OR cr.name LIKE '%speed%' OR cr.name LIKE '%Speed%')",
        class_id, level)


def gather_owner_grants(access: ValidatorAccess, sheet: dict) -> list:
    """Collect all grant_speed rows for every character owner in the sheet.

    A shared retrieval walker (no rule math): both the derivation engine and the movement check read
    the same owner set from the DB, then each resolves the speeds independently (T78/T96)."""
    rows: list = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")

    spid = access.resolve("species", species_name)
    if spid:
        rows.extend(speed_grants(access, "species", spid))

    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            rows.extend(speed_grants(access, "lineage", lid))
            parent_spid = lineage_parent_species(access, lid)
            if parent_spid and parent_spid != spid:
                rows.extend(speed_grants(access, "species", parent_spid))

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
            rows.extend(speed_grants(access, "class", cid, level))
            sub = c.get("subclass")
            if sub:
                sid = access.resolve("subclass", sub)
                if sid:
                    rows.extend(speed_grants(access, "subclass", sid, level))

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = access.resolve("feat", f.get("name"))
            if fid:
                rows.extend(speed_grants(access, "feat", fid))

    # magic items
    from access import primitives
    rows.extend(primitives.item_grants_for(access.db, sheet, "grant_speed", access.resolver))

    return rows


def gather_class_bonuses(access: ValidatorAccess, sheet: dict) -> list[int]:
    """Collect per-class speed bonuses (e.g. an unarmoured-movement class resource) for every class
    owner in the sheet. Shared retrieval walker; the resolver decides how they combine (T78/T96)."""
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
            bonus = class_speed_bonus(access, cid, level)
            if bonus is not None:
                bonuses.append(bonus)

    return bonuses
