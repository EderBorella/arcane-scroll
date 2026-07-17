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


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    expected = _resolve_senses(q.gather_owner_grants(access, sheet))
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
