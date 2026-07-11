"""Weapon Mastery domain: when a "Weapon Mastery" feature is present, validate the
populated top-level ``weapon_masteries`` list against the masterable-weapon set.

The chosen weapons live on the sheet's own ``weapon_masteries`` field (not buried
in a feature's ``choices``): ``mastery-choices-missing`` fires only when that field
is empty while the feature is present, and ``mastery-choice-invalid`` fires for any
entry that is not a masterable weapon."""
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

    return v
