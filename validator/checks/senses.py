"""Senses domain: special-sense range resolution (darkvision, blindsight, etc.) from the grant-sense
spine. The core rule: multiple non-extending grants of the same sense are alternatives — take the
max. Extending grants (extends_existing=1) add on top of a base that must already exist.

This check was deferred as F05-T23 from S12 part 1 — the DB had the data, but no code read or
resolved the grant_sense rows."""
from access.validator import senses as q
from validator.report import Violation

DOMAIN = "senses"


def _resolve_senses(grant_rows: list) -> dict[str, int]:
    """Max-not-sum resolver: for each sense_id, the max of extends_existing=0 rows + the sum of
    extends_existing=1 rows (applied only when a base exists)."""
    bases: dict[str, int] = {}
    extensions: dict[str, int] = {}

    for row in grant_rows:
        sid = row["sense_id"]
        rng = row["range_ft"]
        if row["extends_existing"]:
            extensions[sid] = extensions.get(sid, 0) + rng
        else:
            bases[sid] = max(bases.get(sid, 0), rng)

    result: dict[str, int] = {}
    for sid, base in bases.items():
        result[sid] = base + extensions.get(sid, 0)
    return result


def _gather_owner_grants(access, sheet: dict) -> list:
    """Collect all grant_sense rows for every character owner in the sheet."""
    rows: list = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}

    species_name = ident.get("species")

    # species
    spid = access.resolve("species", species_name)
    if spid:
        rows.extend(q.sense_grants(access, "species", spid))

    # lineage (a subspecies may override or extend a species sense range). The canonical carrier is
    # the dedicated identity.lineage field (mirrors the defenses/movement walkers); the species-name
    # fallback below stays for sheets that instead put a lineage identifier in identity.species.
    lineage_name = ident.get("lineage")
    if isinstance(lineage_name, str) and lineage_name:
        lid = access.resolve("lineage", lineage_name)
        if lid:
            rows.extend(q.sense_grants(access, "lineage", lid))
    if isinstance(species_name, str) and species_name:
        try:
            lid = access.resolve("lineage", species_name)
        except Exception:
            lid = None
        if lid:
            rows.extend(q.sense_grants(access, "lineage", lid))

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
            rows.extend(q.sense_grants(access, "class", cid, level))
            sub = c.get("subclass")
            if sub:
                sid = access.resolve("subclass", sub)
                if sid:
                    rows.extend(q.sense_grants(access, "subclass", sid, level))

    # feats (top-level feats array)
    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if not isinstance(f, dict):
                continue
            fid = access.resolve("feat", f.get("name"))
            if fid:
                rows.extend(q.sense_grants(access, "feat", fid))

    # magic items (equipped + backpack)
    from access import primitives
    rows.extend(primitives.item_grants_for(access.db, sheet, "grant_sense", access.resolver))

    return rows


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    expected = _resolve_senses(_gather_owner_grants(access, sheet))
    sheet_senses = sheet.get("senses")
    if not isinstance(sheet_senses, dict):
        sheet_senses = {}

    known_ids = set(q.sense_ids(access))

    for sense_id, expected_range in expected.items():
        actual = sheet_senses.get(sense_id)
        if actual is None:
            v.append(Violation(DOMAIN, "sense-missing", "incomplete",
                               f"expected {sense_id} {expected_range}ft, not on sheet",
                               f"senses.{sense_id}"))
        elif not isinstance(actual, int) or isinstance(actual, bool):
            v.append(Violation(DOMAIN, "sense-bad-value", "illegal",
                               f"{sense_id}: expected {expected_range}ft, got {actual!r}",
                               f"senses.{sense_id}"))
        elif actual != expected_range:
            v.append(Violation(DOMAIN, "sense-range-mismatch", "illegal",
                               f"{sense_id}: expected {expected_range}ft, got {actual}ft",
                               f"senses.{sense_id}"))

    for sense_id, actual in sheet_senses.items():
        if sense_id not in expected and sense_id in known_ids:
            if isinstance(actual, int) and not isinstance(actual, bool):
                v.append(Violation(DOMAIN, "sense-ungranted", "illegal",
                                   f"{sense_id} {actual}ft: no grant found for this sense",
                                   f"senses.{sense_id}"))

    return v
