"""Resources domain: a CORE ``resource_budgets`` entry that maps to a class/subclass resource with a
count ladder must declare the maximum that ladder confers at the build's level.

The check re-derives the expected maximum independently from the class-resource ladder in the DB —
it never reads the deriver. It is scoped to the class-resource ladder: budget entries for pools,
dice, or formula-based uses the ladder does not model (an entry whose name matches no count-ladder
resource this build owns) are outside its remit and are left alone, rather than the check being
weakened to wave through a wrong ladder maximum."""
import re

from access.validator import resources as q
from validator.report import Violation

DOMAIN = "resources"


def _norm(name: str) -> str:
    """A loose key for matching a sheet's display label to a resource name: lower-cased, with any
    parenthetical qualifier and non-alphanumerics dropped and a trailing plural 's' removed (so a
    singular label matches its plural DB name, and casing/spacing differences collapse)."""
    s = re.sub(r"\(.*?\)", "", name.lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    return s[:-1] if s.endswith("s") else s


def _owned_count_maxima(sheet: dict, access) -> dict[str, int]:
    """{normalised-resource-name: expected max} for every count-ladder resource this build's classes
    and subclasses confer at their levels. On a name collision across a multiclass (two classes with
    a same-named resource) the larger maximum wins."""
    owned: dict[str, int] = {}
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        return owned
    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        cid = access.resolve("class", c.get("class"))
        sub_id = access.resolve("subclass", c.get("subclass"))
        for owner_kind, owner_id in (("class", cid), ("subclass", sub_id)):
            if not owner_id:
                continue
            for res in q.count_class_resources(access, owner_kind, owner_id):
                cnt = q.resource_count_at(access, res["id"], level)
                if cnt is None:
                    continue
                nk = _norm(res["name"])
                if nk not in owned or cnt > owned[nk]:
                    owned[nk] = cnt
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

    owned = _owned_count_maxima(sheet, access)
    for key, budget in budgets.items():
        if not isinstance(budget, dict):
            continue
        nk = _norm(key)
        if nk not in owned:
            continue  # not a class-resource-ladder pool — outside this check's remit
        declared = budget.get("max")
        if not (isinstance(declared, int) and not isinstance(declared, bool)):
            continue
        expected = owned[nk]
        if declared != expected:
            v.append(Violation(DOMAIN, "resource-max-wrong", "illegal",
                               f"{key}: budget max {declared} does not match the {expected} the "
                               "class-resource ladder confers at this level",
                               f"resource_budgets.{key}"))
    return v
