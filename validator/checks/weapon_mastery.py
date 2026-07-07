"""Weapon Mastery domain: validate that "Weapon Mastery" feature choices are valid weapon IDs
that have mastery properties in the weapon table."""
from access.validator import proficiencies as q
from validator.report import Violation

DOMAIN = "weapon_mastery"


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    masterable = q.masterable_weapon_ids(access)

    features = sheet.get("features")
    if not isinstance(features, list):
        return v

    for i, feat in enumerate(features):
        if not isinstance(feat, dict):
            continue
        name = feat.get("name")
        if not isinstance(name, str) or name.strip().lower() != "weapon mastery":
            continue

        choices = feat.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            v.append(Violation(
                DOMAIN, "mastery-choices-missing", "incomplete",
                "'Weapon Mastery' feature present but has no choices",
                f"features[{i}].choices"))
            continue

        for j, choice in enumerate(choices):
            if not isinstance(choice, str) or not choice.strip():
                v.append(Violation(
                    DOMAIN, "mastery-choice-invalid", "illegal",
                    f"invalid mastery choice: {choice!r}",
                    f"features[{i}].choices[{j}]"))
                continue
            if choice.strip().lower() not in masterable:
                v.append(Violation(
                    DOMAIN, "mastery-choice-invalid", "illegal",
                    f"'{choice}' is not a valid masterable weapon",
                    f"features[{i}].choices[{j}]"))

    return v
