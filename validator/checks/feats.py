"""Feats domain: feat legality (resolvable, non-repeatable feats not repeated), prerequisite
eligibility, and a ceiling check of taken feats against available ASI/Epic-Boon and origin-feat
slots. Every expectation is derived from the DB; malformed sheet data becomes a structured finding
rather than a raise.

Prerequisite eligibility is AND across distinct `any_of_group` values and OR within a group. A
`level` row is satisfied by `total_level >= min_level`; an `ability` row is satisfied by the sheet
ability resolving to `ability_id` having `final >= min_score`. Any other kind (note-only, armor) is
treated as satisfied -- it isn't mechanically verifiable from the sheet, and a false positive there
would be worse than silently accepting it.

Slot counting is a ceiling check only, not exact per-feat attribution: fighting-style feats (granted
by a class feature, not spent from a pool) are excluded; origin-category feats are counted against
the (at most 1) origin-feat grant from background/species; everything else (general, epic-boon) is
counted against the ASI/Epic-Boon slots opened up by class levels. Being under a slot budget is not
flagged -- an open slot may legitimately be spent on a raw ability-score increase instead of a feat."""
from access.validator import abilities as abilities_q
from access.validator import feats as q
from validator.report import Violation

DOMAIN = "feats"


def _ident(sheet: dict) -> dict:
    ident = sheet.get("identity", {}) or {}
    return ident if isinstance(ident, dict) else {}


def _classes(ident: dict) -> list:
    raw = ident.get("classes")
    return raw if isinstance(raw, list) else []


def _total_level(ident: dict) -> int:
    declared = ident.get("total_level")
    if isinstance(declared, int) and not isinstance(declared, bool):
        return declared
    total = 0
    for c in _classes(ident):
        if not isinstance(c, dict):
            continue
        lvl = c.get("level")
        if isinstance(lvl, int) and not isinstance(lvl, bool):
            total += lvl
    return total


def _ability_final(access, abilities_sheet: dict, ability_id: str | None) -> int | None:
    if ability_id is None or not isinstance(abilities_sheet, dict):
        return None
    for k, entry in abilities_sheet.items():
        if not isinstance(entry, dict):
            continue
        if abilities_q.ability_id(access, k) != ability_id:
            continue
        final = entry.get("final")
        if isinstance(final, int) and not isinstance(final, bool):
            return final
    return None


def _normalise(raw: list, v: list[Violation]) -> list[tuple[str | None, str]]:
    """[(name, path), ...] for each feats entry; malformed entries get a finding and are dropped."""
    out = []
    for i, entry in enumerate(raw):
        path = f"feats[{i}]"
        if isinstance(entry, str):
            out.append((entry, path))
        elif isinstance(entry, dict):
            out.append((entry.get("name"), path))
        else:
            v.append(Violation(DOMAIN, "malformed-feat", "illegal",
                               f"feat entry must be a string or object with a name, got {entry!r}", path))
    return out


def _resolve_feats(names: list[tuple[str | None, str]], access,
                   v: list[Violation]) -> list[tuple[str, object, str]]:
    """[(feat_id, feat_row, path), ...] for the names that resolve to a known feat."""
    out = []
    for name, path in names:
        fid = access.resolve("feat", name)
        if fid is None:
            v.append(Violation(DOMAIN, "unknown-feat", "illegal", f"unknown feat: {name!r}", path))
            continue
        row = q.feat_row(access, fid)
        if row is None:
            continue
        out.append((fid, row, path))
    return out


def _check_repeats(resolved: list[tuple[str, object, str]], v: list[Violation]) -> None:
    counts: dict[str, int] = {}
    for fid, _row, _path in resolved:
        counts[fid] = counts.get(fid, 0) + 1
    flagged: set[str] = set()
    for fid, row, path in resolved:
        if counts[fid] > 1 and not row["repeatable"] and fid not in flagged:
            v.append(Violation(DOMAIN, "feat-repeated", "illegal",
                               f"{row['name']}: not repeatable but appears {counts[fid]} times", path))
            flagged.add(fid)


def _check_prereqs(resolved: list[tuple[str, object, str]], access, ident: dict,
                   abilities_sheet: dict, v: list[Violation]) -> None:
    total_level = _total_level(ident)
    for fid, row, path in resolved:
        prereqs = q.feat_prereqs(access, fid)
        if not prereqs:
            continue
        groups: dict[object, list] = {}
        for pr in prereqs:
            groups.setdefault(pr["any_of_group"], []).append(pr)

        unmet: list[str] = []
        for group_id, rows in groups.items():
            satisfied = False
            descriptions = []
            for pr in rows:
                kind = pr["kind"]
                if kind == "level":
                    min_level = pr["min_level"]
                    descriptions.append(f"total level >= {min_level}")
                    if isinstance(min_level, int) and not isinstance(min_level, bool) \
                            and total_level >= min_level:
                        satisfied = True
                elif kind == "ability":
                    ability_id = pr["ability_id"]
                    min_score = pr["min_score"]
                    descriptions.append(f"ability {ability_id} >= {min_score}")
                    final = _ability_final(access, abilities_sheet, ability_id)
                    if final is not None and isinstance(min_score, int) \
                            and not isinstance(min_score, bool) and final >= min_score:
                        satisfied = True
                else:
                    # note-only / armor prereqs aren't mechanically verifiable from the sheet --
                    # treat as satisfied rather than risk a false positive.
                    satisfied = True
            if not satisfied:
                unmet.append(" or ".join(descriptions) if descriptions else f"group {group_id}")

        if unmet:
            v.append(Violation(DOMAIN, "feat-prereq-unmet", "illegal",
                               f"{row['name']}: unmet prerequisite ({'; '.join(unmet)})", path))


def _asi_budget(ident: dict, access) -> int:
    budget = 0
    for c in _classes(ident):
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        n = q.asi_slots(access, cid, level)
        budget += n or 0
    return budget


def _origin_budget(ident: dict, access) -> int:
    bg_id = access.resolve("background", ident.get("background"))
    if bg_id is not None and q.background_origin_feat(access, bg_id) is not None:
        return 1
    sp_id = access.resolve("species", ident.get("species"))
    if sp_id is not None and q.grants_origin_feat(access, "species", sp_id):
        return 1
    return 0


def _check_slots(resolved: list[tuple[str, object, str]], ident: dict, access, v: list[Violation]) -> None:
    asi_count = 0
    origin_count = 0
    for _fid, row, _path in resolved:
        category = row["category"]
        if category == "fighting-style":
            continue
        elif category == "origin":
            origin_count += 1
        else:
            asi_count += 1

    origin_budget = _origin_budget(ident, access)
    if origin_count > origin_budget:
        v.append(Violation(DOMAIN, "too-many-origin-feats", "illegal",
                           f"{origin_count} origin feats exceeds the budget of {origin_budget}", "feats"))

    asi_budget = _asi_budget(ident, access)
    if asi_count > asi_budget:
        v.append(Violation(DOMAIN, "too-many-feats", "illegal",
                           f"{asi_count} feats exceeds the available ASI/Epic-Boon slot budget of {asi_budget}",
                           "feats"))


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    raw = sheet.get("feats", []) or []
    if not isinstance(raw, list):
        v.append(Violation(DOMAIN, "malformed-feats", "illegal", "feats must be a list", "feats"))
        return v

    ident = _ident(sheet)
    abilities_sheet = sheet.get("abilities")
    if not isinstance(abilities_sheet, dict):
        abilities_sheet = {}

    names = _normalise(raw, v)
    resolved = _resolve_feats(names, access, v)

    _check_repeats(resolved, v)
    _check_prereqs(resolved, access, ident, abilities_sheet, v)
    _check_slots(resolved, ident, access, v)

    return v
