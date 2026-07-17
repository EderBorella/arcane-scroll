"""Resources domain: a CORE ``resource_budgets`` entry that maps to a resource this build owns must
declare the maximum that resource confers.

The check re-derives every expected maximum independently from the DB — it never reads the deriver.
It covers two owned-resource sources:

* the **class-resource COUNT ladder** — the maximum a class/subclass count ladder confers at the
  build's level.
* the **``grant_resource`` use-pool spine** — a species- or lineage-owned use pool whose maximum is a
  fixed count (``int``), the proficiency bonus (re-derived from total level), or an ability modifier
  (re-derived from the sheet's abilities, minimum one).

A budget entry whose name matches no resource this build owns (a pool, a pure die/bonus magnitude, or
a feature use the DB does not model as a queryable maximum) is outside the check's remit and is left
alone, rather than the check being weakened to wave through a wrong maximum."""
import re

from access.validator import resources as q
from validator.report import Violation

DOMAIN = "resources"


def _proficiency_bonus(total_level: int) -> int:
    """Proficiency bonus re-derived from total level (independent of the deriver)."""
    return 2 + (max(1, total_level) - 1) // 4


def _norm(name: str) -> str:
    """A loose key for matching a sheet's display label to a resource name: lower-cased, with any
    parenthetical qualifier and non-alphanumerics dropped and a trailing plural 's' removed (so a
    singular label matches its plural DB name, and casing/spacing differences collapse)."""
    s = re.sub(r"\(.*?\)", "", name.lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    return s[:-1] if s.endswith("s") else s


def _grant_resource_max(res: dict, proficiency_bonus: int, ability_mods: dict) -> int | None:
    """The maximum a ``grant_resource`` use-pool confers, re-derived from its ``uses_kind`` (kept
    independent of the deriver): ``int`` -> the fixed ``uses_num``; ``proficiency_bonus`` -> the
    proficiency bonus; ``ability_modifier`` -> the named ability modifier, minimum one."""
    kind = res.get("uses_kind")
    if kind == "int":
        n = res.get("uses_num")
        return n if isinstance(n, int) and not isinstance(n, bool) else None
    if kind == "proficiency_bonus":
        return proficiency_bonus
    if kind == "ability_modifier":
        return max(1, ability_mods.get(res.get("uses_ability_id"), 0))
    return None


def _ability_mods(sheet: dict, access) -> dict[str, int]:
    """{ability_id: modifier} re-derived from the sheet's abilities (keyed there by abbreviation)."""
    mods: dict[str, int] = {}
    abilities = sheet.get("abilities")
    if not isinstance(abilities, dict):
        return mods
    for aid_row in access.db.q("SELECT id, abbrev FROM ability"):
        entry = abilities.get((aid_row["abbrev"] or "").lower())
        if isinstance(entry, dict) and isinstance(entry.get("final"), int):
            mods[aid_row["id"]] = (entry["final"] - 10) // 2
    return mods


def _owned_maxima(sheet: dict, access) -> dict[str, int]:
    """{normalised-resource-name: expected max} for every resource this build owns — count-ladder
    class/subclass resources at their levels, plus species/lineage ``grant_resource`` use-pools. On a
    name collision the larger maximum wins."""
    owned: dict[str, int] = {}
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        return owned

    def put(name: str, value: int) -> None:
        nk = _norm(name)
        if nk not in owned or value > owned[nk]:
            owned[nk] = value

    total_level = 0
    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        total_level += level
        cid = access.resolve("class", c.get("class"))
        sub_id = access.resolve("subclass", c.get("subclass"))
        for owner_kind, owner_id in (("class", cid), ("subclass", sub_id)):
            if not owner_id:
                continue
            for res in q.count_class_resources(access, owner_kind, owner_id):
                cnt = q.resource_count_at(access, res["id"], level)
                if cnt is not None:
                    put(res["name"], cnt)

    # species / lineage grant_resource use-pools, re-derived from DB facts.
    pb = _proficiency_bonus(total_level)
    ability_mods = _ability_mods(sheet, access)
    owners: list[tuple[str, str | None]] = [
        ("species", access.resolve("species", ident.get("species"))),
        ("lineage", access.resolve("lineage", ident.get("lineage"))),
    ]
    for owner_kind, owner_id in owners:
        if not owner_id:
            continue
        for res in q.grant_resources(access, owner_kind, owner_id, at_level=total_level):
            value = _grant_resource_max(res, pb, ability_mods)
            if value is not None:
                put(res["name"], value)
    return owned


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    budgets = sheet.get("resource_budgets")
    if budgets is None:
        return v
    if not isinstance(budgets, dict):
        v.append(Violation(DOMAIN, "malformed-resource-budgets", "illegal",
                           "resource_budgets must be an object", "resource_budgets"))
        return v

    owned = _owned_maxima(sheet, access)
    for key, budget in budgets.items():
        if not isinstance(budget, dict):
            continue
        nk = _norm(key)
        if nk not in owned:
            continue  # not a resource this check can re-derive — outside its remit
        declared = budget.get("max")
        if not (isinstance(declared, int) and not isinstance(declared, bool)):
            continue
        expected = owned[nk]
        if declared != expected:
            v.append(Violation(DOMAIN, "resource-max-wrong", "illegal",
                               f"{key}: budget max {declared} does not match the {expected} this "
                               "resource confers for the build",
                               f"resource_budgets.{key}"))
    return v
