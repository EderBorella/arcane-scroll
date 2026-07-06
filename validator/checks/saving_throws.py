"""Saving-throws domain: proficiency and modifier consistency against the union of the first
class's class_saving_throw rows (the 2024 first-class-grants-saves rule) and any saving-throw
proficiency granted by a feat (e.g. Resilient), the species, or a class's subclass (e.g. Gloom
Stalker's Wisdom save). Every expectation is derived from the DB; malformed or missing sheet data
is skipped rather than raised."""
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
    if not isinstance(ident, dict):
        ident = {}
    classes = ident.get("classes")
    if not isinstance(classes, list) or not classes or not isinstance(classes[0], dict):
        return v

    cid = access.resolve("class", classes[0].get("class"))
    if cid is None:
        return v
    expected_saves = set(q.class_save_abilities(access, cid))

    sp_id = access.resolve("species", ident.get("species"))
    if sp_id is not None:
        expected_saves |= set(q.granted_save_abilities(access, "species", sp_id))

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            feat_id = access.resolve("feat", f)
            if feat_id is not None:
                expected_saves |= set(q.granted_save_abilities(access, "feat", feat_id))

    for c in classes:
        if not isinstance(c, dict):
            continue
        sub = c.get("subclass")
        if not sub:
            continue
        sub_id = access.resolve("subclass", sub)
        if sub_id is not None:
            expected_saves |= set(q.granted_save_abilities(access, "subclass", sub_id))

    abilities_sheet = sheet.get("abilities")
    pb = sheet.get("proficiency_bonus")

    for k, entry in saves.items():
        if not isinstance(entry, dict):
            continue
        path = f"saving_throws.{k}"
        aid = abilities_q.ability_id(access, k)
        if aid is None:
            continue
        expected = aid in expected_saves

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
