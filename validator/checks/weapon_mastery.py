"""Weapon Mastery domain: when a "Weapon Mastery" feature is present, validate the
populated top-level ``weapon_masteries`` list against the masterable-weapon set AND
against the DB-derived allowance (how many the build's classes entitle it to).

The chosen weapons live on the sheet's own ``weapon_masteries`` field (not buried
in a feature's ``choices``): ``mastery-choices-missing`` fires only when that field
is empty while the feature is present, ``mastery-choice-invalid`` fires for any
entry that is not a masterable weapon, and ``mastery-count-mismatch`` fires when the
number of entries differs from the DB-derived allowance.

Allowance derivation (re-derived from the DB, never from the generator): each class
confers a weapon-mastery count read from its own resource ladder at its own level.
Across a multiclass build those counts STACK (sum), because the ruleset's
multiclassing rules only special-case the non-stacking features (the extra-attack
family, the spellcasting combine, and the alternative armour-class calculations) --
this normal per-class feature is not among them, so the general rule ("gain each
class's features for its level") applies and each class's allowance adds. The total
is capped at the masterable-weapon pool size (a build cannot master more distinct
weapons than carry a mastery property). When no class confers a count, there is
nothing to assert and the count check is skipped."""
from access.validator import proficiencies as q
from validator.report import Violation

DOMAIN = "weapon_mastery"


def _has_weapon_mastery_feature(features) -> bool:
    if not isinstance(features, list):
        return False
    for feat in features:
        if not isinstance(feat, dict):
            continue
        name = feat.get("name")
        if isinstance(name, str) and name.strip().lower() == "weapon mastery":
            return True
    return False


def _resolved_class_levels(sheet: dict, access) -> list[tuple[str, int]]:
    """[(class_id, level), ...] for the build's classes that resolve cleanly; malformed or unknown
    entries are skipped rather than raised."""
    ident = sheet.get("identity")
    if not isinstance(ident, dict):
        return []
    classes = ident.get("classes")
    if not isinstance(classes, list):
        return []
    out: list[tuple[str, int]] = []
    for c in classes:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not isinstance(level, int) or isinstance(level, bool):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        out.append((cid, level))
    return out


def _expected_mastery_count(sheet: dict, access) -> int | None:
    """The weapon-mastery allowance the build's classes confer -- the SUM of each class's count at its
    OWN level (the counts stack across classes; see the module docstring), capped at the
    masterable-weapon pool size. None when no class confers a count (nothing to assert)."""
    total = sum(q.weapon_mastery_count(access, cid, lvl)
                for cid, lvl in _resolved_class_levels(sheet, access))
    if total <= 0:
        return None
    pool = q.masterable_weapon_count(access)
    return min(total, pool) if pool else total


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    if not _has_weapon_mastery_feature(sheet.get("features")):
        return v

    masteries = sheet.get("weapon_masteries")
    if not isinstance(masteries, list) or len(masteries) == 0:
        v.append(Violation(
            DOMAIN, "mastery-choices-missing", "incomplete",
            "'Weapon Mastery' feature present but weapon_masteries is empty",
            "weapon_masteries"))
        return v

    masterable = q.masterable_weapon_ids(access)
    for j, choice in enumerate(masteries):
        if not isinstance(choice, str) or not choice.strip():
            v.append(Violation(
                DOMAIN, "mastery-choice-invalid", "illegal",
                f"invalid mastery choice: {choice!r}",
                f"weapon_masteries[{j}]"))
            continue
        if choice.strip().lower() not in masterable:
            v.append(Violation(
                DOMAIN, "mastery-choice-invalid", "illegal",
                f"'{choice}' is not a valid masterable weapon",
                f"weapon_masteries[{j}]"))

    expected = _expected_mastery_count(sheet, access)
    if expected is not None and len(masteries) != expected:
        severity = "incomplete" if len(masteries) < expected else "illegal"
        v.append(Violation(
            DOMAIN, "mastery-count-mismatch", severity,
            f"expected {expected} weapon-mastery choice(s) but found {len(masteries)}",
            "weapon_masteries"))

    return v
