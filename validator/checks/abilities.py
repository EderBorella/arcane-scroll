"""Abilities domain: ability-key resolution, modifier consistency, the standard score cap, and
background-boost legality. Every expectation is derived from the DB."""
from access.validator import abilities as q
from validator.report import Violation

DOMAIN = "abilities"

_VALID_BOOST_SHAPES = ([1, 1, 1], [1, 2])


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    abilities = sheet.get("abilities")
    if not isinstance(abilities, dict):
        v.append(Violation(DOMAIN, "malformed-abilities", "illegal",
                           "abilities must be a dict", "abilities"))
        return v

    cap = q.standard_ability_cap(access)
    resolved: set[str] = set()
    boosts: list[tuple[int, str]] = []

    for k, entry in abilities.items():
        path = f"abilities.{k}"
        aid = q.ability_id(access, k)
        if aid is None:
            v.append(Violation(DOMAIN, "unknown-ability", "illegal",
                               f"unknown ability: {k!r}", path))
            continue
        resolved.add(aid)
        if not isinstance(entry, dict):
            continue

        final = entry.get("final")
        modifier = entry.get("modifier")
        if (isinstance(final, int) and not isinstance(final, bool)
                and isinstance(modifier, int) and not isinstance(modifier, bool)):
            if modifier != (final - 10) // 2:
                v.append(Violation(DOMAIN, "modifier-mismatch", "illegal",
                                   f"{k}: modifier {modifier} does not match final score {final}", path))
            if cap is not None and final > cap:
                v.append(Violation(DOMAIN, "ability-over-cap", "illegal",
                                   f"{k}: final score {final} exceeds the standard cap {cap} "
                                   "(item-set exceptions are checked in the items domain)", path))

        bonus = entry.get("background_bonus")
        if bonus is not None:
            if isinstance(bonus, int) and not isinstance(bonus, bool):
                if bonus:
                    boosts.append((bonus, aid))
            else:
                v.append(Violation(DOMAIN, "background-bonus-malformed", "illegal",
                                   f"background_bonus must be an integer, got {bonus!r}", f"{path}.background_bonus"))

    missing = set(q.all_ability_ids(access)) - resolved
    if missing:
        v.append(Violation(DOMAIN, "missing-ability", "incomplete",
                           f"missing ability entries: {sorted(missing)}", "abilities"))

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    bg_id = access.resolve("background", ident.get("background"))
    if bg_id is not None:
        if not boosts:
            v.append(Violation(DOMAIN, "background-boost-missing", "incomplete",
                               "background ability boosts (total 3) are expected but none are declared",
                               "abilities"))
        else:
            allowed = set(q.background_boost_abilities(access, bg_id))
            bad_target = any(aid not in allowed for _, aid in boosts)
            values = sorted(b for b, _ in boosts)
            if bad_target or values not in _VALID_BOOST_SHAPES:
                v.append(Violation(DOMAIN, "background-boost-illegal", "illegal",
                                   "background ability boosts must total 3 points, as {2,1} or {1,1,1}, "
                                   "all on abilities the background allows", "abilities"))
    return v
