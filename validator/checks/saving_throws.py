"""Saving-throws domain: proficiency and modifier consistency against the first class's
class_saving_throw rows (the 2024 first-class-grants-saves rule). Every expectation is derived
from the DB; malformed or missing sheet data is skipped rather than raised."""
from access.validator import abilities as abilities_q
from access.validator import saving_throws as q
from validator.report import Violation

DOMAIN = "saving_throws"


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    saves = sheet.get("saving_throws")
    if not isinstance(saves, dict):
        return v

    ident = sheet.get("identity", {}) or {}
    classes = ident.get("classes")
    if not isinstance(classes, list) or not classes or not isinstance(classes[0], dict):
        return v

    cid = access.resolve("class", classes[0].get("class"))
    if cid is None:
        return v
    class_saves = set(q.class_save_abilities(access, cid))

    abilities_sheet = sheet.get("abilities")
    pb = sheet.get("proficiency_bonus")

    for k, entry in saves.items():
        if not isinstance(entry, dict):
            continue
        path = f"saving_throws.{k}"
        aid = abilities_q.ability_id(access, k)
        if aid is None:
            continue
        expected = aid in class_saves

        proficient = entry.get("proficient")
        if proficient != expected:
            v.append(Violation(DOMAIN, "save-proficiency-mismatch", "illegal",
                               f"{k}: proficient should be {expected}", path))

        modifier = entry.get("modifier")
        ability_entry = abilities_sheet.get(k) if isinstance(abilities_sheet, dict) else None
        if (isinstance(ability_entry, dict) and isinstance(ability_entry.get("final"), int)
                and not isinstance(ability_entry.get("final"), bool)
                and isinstance(pb, int) and not isinstance(pb, bool)
                and isinstance(modifier, int) and not isinstance(modifier, bool)):
            ability_mod = (ability_entry["final"] - 10) // 2
            expected_mod = ability_mod + (pb if expected else 0)
            if modifier != expected_mod:
                v.append(Violation(DOMAIN, "save-modifier-mismatch", "illegal",
                                   f"{k}: modifier {modifier} should be {expected_mod}", path))
    return v
