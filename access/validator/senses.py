"""Senses-domain DB facts: grant_sense rows for an owner (species, class, subclass, feat, etc.)."""
from access.validator import ValidatorAccess


def sense_grants(access: ValidatorAccess, owner_kind: str, owner_id: str,
                 at_level: int | None = None) -> list:
    """Raw grant_sense rows for an owner, optionally level-gated."""
    sql = ("SELECT sense_id, range_ft, extends_existing "
           "FROM grant_sense WHERE owner_kind=? AND owner_id=?")
    params = [owner_kind, owner_id]
    if at_level is not None:
        sql += " AND (gained_at_level IS NULL OR gained_at_level<=?)"
        params.append(at_level)
    return access.db.q(sql, *params)


def sense_ids(access: ValidatorAccess) -> list[str]:
    """All known sense ids (for the `senses` key set — detect unknown sense keys on a sheet)."""
    return [r["id"] for r in access.db.q("SELECT id FROM sense")]


def gather_owner_grants(access: ValidatorAccess, sheet: dict) -> list:
    """Collect all grant_sense rows for every character owner in the sheet.

    A shared retrieval walker (no rule math): both the derivation engine and the senses check read
    the same owner set from the DB, then each resolves the ranges independently (T78/T96)."""
    rows: list = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")

    # species
    spid = access.resolve("species", species_name)
    if spid:
        rows.extend(sense_grants(access, "species", spid))

    # lineage (a subspecies may override or extend a species sense range). The canonical carrier is
    # the dedicated identity.lineage field (mirrors the defenses/movement walkers); the species-name
    # fallback below stays for sheets that instead put a lineage identifier in identity.species.
    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            rows.extend(sense_grants(access, "lineage", lid))
    if isinstance(species_name, str) and species_name:
        try:
            lid = access.resolve("lineage", species_name)
        except Exception:
            lid = None
        if lid:
            rows.extend(sense_grants(access, "lineage", lid))

    # classes + subclasses (level-gated)
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
            rows.extend(sense_grants(access, "class", cid, level))
            sub = c.get("subclass")
            if sub:
                sid = access.resolve("subclass", sub)
                if sid:
                    rows.extend(sense_grants(access, "subclass", sid, level))

    # feats (top-level feats array)
    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = access.resolve("feat", f.get("name"))
            if fid:
                rows.extend(sense_grants(access, "feat", fid))

    # magic items (equipped + backpack)
    from access import primitives
    rows.extend(primitives.item_grants_for(access.db, sheet, "grant_sense", access.resolver))

    return rows
