"""Identity domain: class/subclass/species/background/size/creature-type legality, total-level
consistency, subclass-unlock timing, and XP↔level. Every expectation is derived from the DB."""
from access.validator import identity as q
from validator.report import Violation

DOMAIN = "identity"


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    raw_classes = ident.get("classes", []) or []

    total = 0
    if not isinstance(raw_classes, list):
        v.append(Violation(DOMAIN, "malformed-classes", "illegal",
                           "classes must be a list", "identity.classes"))
        classes = []
    else:
        classes = raw_classes

    for i, c in enumerate(classes):
        level = c.get("level")
        if not isinstance(level, int) or isinstance(level, bool):
            v.append(Violation(DOMAIN, "malformed-level", "illegal",
                               f"level must be an integer, got {level!r}", f"identity.classes[{i}].level"))
            level = 0
        total += level or 0
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            v.append(Violation(DOMAIN, "unknown-class", "illegal",
                               f"unknown class: {c.get('class')!r}", f"identity.classes[{i}].class"))
            continue
        lvl = level or 0
        unlock = q.subclass_unlock_level(access, cid)
        sub = c.get("subclass")
        if sub:
            sid = access.resolve("subclass", sub)
            if sid is None:
                v.append(Violation(DOMAIN, "unknown-subclass", "illegal",
                                   f"unknown subclass: {sub!r}", f"identity.classes[{i}].subclass"))
            elif q.subclass_parent(access, sid) != cid:
                v.append(Violation(DOMAIN, "subclass-class-mismatch", "illegal",
                                   f"subclass {sub!r} does not belong to {c.get('class')!r}",
                                   f"identity.classes[{i}].subclass"))
            if unlock is not None and lvl < unlock:
                v.append(Violation(DOMAIN, "subclass-too-early", "illegal",
                                   f"subclass chosen at level {lvl}, available at {unlock}",
                                   f"identity.classes[{i}]"))
        elif unlock is not None and lvl >= unlock:
            v.append(Violation(DOMAIN, "subclass-missing", "incomplete",
                               f"a subclass is expected by level {unlock}", f"identity.classes[{i}]"))

    spid = access.resolve("species", ident.get("species"))
    if spid is None:
        v.append(Violation(DOMAIN, "unknown-species", "illegal",
                           f"unknown species: {ident.get('species')!r}", "identity.species"))
    elif ident.get("creature_type") is not None:
        ctid = access.resolve("creature_type", ident.get("creature_type"))
        if ctid is None:
            v.append(Violation(DOMAIN, "unknown-creature_type", "illegal",
                               f"unknown creature type: {ident.get('creature_type')!r}",
                               "identity.creature_type"))
        elif ctid != q.species_creature_type(access, spid):
            v.append(Violation(DOMAIN, "creature-type-mismatch", "illegal",
                               "creature type does not match the species", "identity.creature_type"))

    if access.resolve("background", ident.get("background")) is None:
        v.append(Violation(DOMAIN, "unknown-background", "illegal",
                           f"unknown background: {ident.get('background')!r}", "identity.background"))

    if ident.get("size") is not None and access.resolve("size", ident.get("size")) is None:
        v.append(Violation(DOMAIN, "unknown-size", "illegal",
                           f"unknown size: {ident.get('size')!r}", "identity.size"))

    declared = ident.get("total_level")
    if declared is not None and declared != total:
        v.append(Violation(DOMAIN, "total-level-mismatch", "illegal",
                           f"total_level {declared} != sum of class levels {total}",
                           "identity.total_level"))

    xp = ident.get("xp")
    if xp is not None and total:
        lo = q.xp_min(access, total)
        hi = q.xp_min(access, total + 1)
        if lo is not None and xp < lo:
            v.append(Violation(DOMAIN, "xp-too-low", "illegal",
                               f"xp {xp} below the level-{total} minimum {lo}", "identity.xp"))
        elif hi is not None and xp >= hi:
            v.append(Violation(DOMAIN, "xp-too-high", "illegal",
                               f"xp {xp} at/above the level-{total + 1} threshold {hi}", "identity.xp"))
    return v
