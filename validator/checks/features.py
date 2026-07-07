"""Features domain: class and subclass feature presence, and detail-option validity.
Species traits are intentionally NOT validated here — other domains (senses, defenses,
movement) already verify their mechanical effects and species traits are listed as
features inconsistently across sheets."""
import re
from collections import Counter

from access.validator import features as q
from validator.report import Violation

DOMAIN = "features"


def _norm_name(name: str) -> str:
    return re.sub(r'\s*\([^)]*\)', '', name).strip().lower()


def _ident(sheet: dict) -> dict:
    ident = sheet.get("identity", {}) or {}
    return ident if isinstance(ident, dict) else {}


def _classes(ident: dict) -> list:
    raw = ident.get("classes")
    return raw if isinstance(raw, list) else []


def _build_expected(access, sheet: dict) -> tuple[Counter[str], list]:
    """Build the expected feature counts from class and subclass features.
    Returns (expected_counts: Counter of normalized_name->count, violations)."""
    v: list[Violation] = []
    expected: Counter[str] = Counter()
    ident = _ident(sheet)

    for c in _classes(ident):
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid:
            for row in q.class_features(access, cid, level):
                expected[_norm_name(row["name"])] += 1

        sub = c.get("subclass")
        if sub:
            sid = access.resolve("subclass", sub)
            if sid:
                for row in q.subclass_features(access, sid, level):
                    expected[_norm_name(row["name"])] += 1

                subclass_detail = c.get("subclass_detail")
                if subclass_detail and isinstance(subclass_detail, str):
                    options = q.detail_options(access, "subclass", sid)
                    valid_names = {_norm_name(row["name"]) for row in options}
                    if valid_names and _norm_name(subclass_detail) not in valid_names:
                        v.append(Violation(
                            DOMAIN, "feature-detail-option-invalid", "illegal",
                            f"subclass_detail '{subclass_detail}' is not a valid option for {sub}",
                            f"identity.classes.{c.get('class')}.subclass_detail"))

    return expected, v


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    expected_counts, ve = _build_expected(access, sheet)
    v.extend(ve)

    sheet_features = sheet.get("features")
    if sheet_features is None:
        sheet_features = []
    if not isinstance(sheet_features, list):
        v.append(Violation(DOMAIN, "malformed-features", "illegal",
                           "features must be a list", "features"))
        return v

    sheet_counts: Counter[str] = Counter()
    for i, feat in enumerate(sheet_features):
        if not isinstance(feat, dict):
            v.append(Violation(DOMAIN, "malformed-feature", "illegal",
                               f"feature entry must be an object, got {feat!r}", f"features[{i}]"))
            continue
        name = feat.get("name")
        if not isinstance(name, str):
            v.append(Violation(DOMAIN, "malformed-feature", "illegal",
                               f"feature entry missing name, got {feat!r}", f"features[{i}]"))
            continue
        sheet_counts[_norm_name(name)] += 1

    for norm_name, expected_count in expected_counts.items():
        sheet_count = sheet_counts.get(norm_name, 0)
        if sheet_count < expected_count:
            v.append(Violation(DOMAIN, "feature-missing", "incomplete",
                               f"expected {expected_count} instance(s) of '{norm_name}', sheet has {sheet_count}",
                               "features"))

    for norm_name, sheet_count in sheet_counts.items():
        if norm_name not in expected_counts:
            v.append(Violation(DOMAIN, "feature-ungranted", "illegal",
                               f"feature '{norm_name}' on sheet but not granted by any class or subclass",
                               "features"))

    return v
