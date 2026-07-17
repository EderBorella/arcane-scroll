"""Saving-throws domain: proficiency and modifier consistency against the union of the first
class's class_saving_throw rows (the first-class-grants-saves rule) and any saving-throw
proficiency granted by a feat, the species, a class's subclass, or a class's own level-gated
feature (a high-level feature that grants extra saves, applied to every class entry -- not just the
first -- gated by that entry's level). Every
expectation is derived from the DB; malformed or missing sheet data is skipped rather than raised."""
from access.validator import abilities as abilities_q
from access.validator import saving_throws as q
from validator.report import Violation

DOMAIN = "saving_throws"


def _feat_name(entry):
    """A feats entry may be a bare name (string) or an object carrying a `name` field (the
    top-level-fields sheet shape). Return the name to hand to the resolver, or None if the entry
    carries no usable name -- passing the raw object to the resolver never resolves, silently
    dropping any proficiency the feat grants."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("name")
    return None


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
            feat_id = access.resolve("feat", _feat_name(f))
            if feat_id is not None:
                expected_saves |= set(q.granted_save_abilities(access, "feat", feat_id))

    for c in classes:
        if not isinstance(c, dict):
            continue
        # Gate a grant by the level of the class entry that owns it (a subclass or class feature
        # granting saves only from a given level onward) -- a malformed or missing level
        # defensively counts as 0, so only always-on (NULL gained_at_level) grants apply.
        c_level = c.get("level")
        c_at_level = c_level if isinstance(c_level, int) and not isinstance(c_level, bool) else 0

        # A class's own level-gated feature save grant, applied to EVERY class entry (including a
        # non-first class), not only the first-class-grants-saves rows.
        c_id = access.resolve("class", c.get("class"))
        if c_id is not None:
            expected_saves |= set(q.granted_save_abilities(access, "class", c_id, at_level=c_at_level))

        sub = c.get("subclass")
        if not sub:
            continue
        sub_id = access.resolve("subclass", sub)
        if sub_id is not None:
            expected_saves |= set(q.granted_save_abilities(access, "subclass", sub_id, at_level=c_at_level))

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
