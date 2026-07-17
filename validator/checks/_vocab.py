"""Shared vocabulary normalisers for the check layer.

The corpus and the reference DB carry two forms of the same armour/item category: a short display
form on older sheets (``heavy``, ``light``, ``shield``) and the DB id (``heavy-armor``,
``light-armor``, ``shield``). Any check that compares a sheet-supplied category against a DB category
routes BOTH sides through :func:`armor_category_id`, so the two forms compare equal without touching
the corpus or the DB. Pure string mapping -- no DB access, no rule math.
"""


def armor_category_id(name: str) -> str:
    """Normalise an armour/item category name (short display form or DB id) to its armor_category id.

    Idempotent on ids already in canonical form (``heavy-armor`` -> ``heavy-armor``), so it is safe to
    apply to both a sheet-supplied value and a DB value at a comparison site.
    """
    n = name.strip().lower()
    if n == "shields":
        n = "shield"
    n = n.replace(" ", "-")
    if n in ("light", "medium", "heavy"):
        n = n + "-armor"
    return n
