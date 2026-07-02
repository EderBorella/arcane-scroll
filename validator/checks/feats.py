"""Layer: feats. Feats taken fit the available feat/ASI slots (one Origin feat from the background +
every Ability-Score-Improvement / Epic-Boon feature the classes have reached); each feat's checkable
prerequisites — minimum character/class level and ability minimums (13+) — are met; and a
non-repeatable feat isn't taken twice. Feature-gated prerequisites (armour training, a spellcasting
feature, an invocation) are not enforced here. Collects all findings; never raises."""
from validator.report import Violation, WARNING

LAYER = "feats"


def check(sheet, rules):
    out = []
    feats = sheet.get("feats")
    if feats is None:
        return out
    ident = sheet.get("identity") or {}
    classes = ident.get("classes") or []
    abilities = sheet.get("abilities") or {}

    # 1) count ≤ available slots (an ASI slot may instead be spent on an ability increase, so ≤)
    slots = rules.feat_slots(classes, bool(ident.get("background")))
    if len(feats) > slots:
        out.append(Violation(LAYER, "feat_slot_overrun",
                             f"{len(feats)} feat(s) taken; only {slots} feat slot(s) available",
                             slots, len(feats)))

    class_level = {(c.get("class") or "").lower(): c.get("level") or 0 for c in classes}
    total = ident.get("total_level")

    seen = {}
    for f in feats:
        name = f.get("name")
        key = (name or "").lower()
        seen[key] = seen.get(key, 0) + 1
        info = rules.feat(name)
        if info is None:
            if rules.feats:      # only flag against loaded feat data
                out.append(Violation(LAYER, "unknown_feat", f"'{name}' is not a known feat",
                                     None, name, severity=WARNING))
            continue
        pre = info.get("prereq") or {}
        req_lvl = pre.get("level")
        if req_lvl is not None:
            klass = pre.get("class")
            have = class_level.get(klass) if klass else total
            if have is not None and have < req_lvl:
                out.append(Violation(LAYER, "feat_prereq_level",
                                     f"feat '{name}' needs {(klass + ' ') if klass else ''}level {req_lvl}+; "
                                     f"character has {have}", req_lvl, have))
        for group in pre.get("abilities", []):
            best = max((abilities.get(ab, {}).get("final", 0) for ab in group), default=0)
            if best < 13:
                out.append(Violation(LAYER, "feat_prereq_ability",
                                     f"feat '{name}' needs one of {group} ≥ 13; highest is {best}",
                                     13, best))

    # 3) a non-repeatable feat taken more than once
    for key, n in seen.items():
        if n > 1:
            info = rules.feat(key)
            if info is not None and not info.get("repeatable"):
                out.append(Violation(LAYER, "feat_repeated",
                                     f"feat '{key}' taken {n} times but is not repeatable", 1, n))
    return out
