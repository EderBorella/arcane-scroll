"""State compatibility queries — which states block or imply other states.

Consumed by the MODIFIER validator to check that ``character_states[]``
entries are mutually compatible (e.g. a character cannot simultaneously
be ``incapacitated`` and ``raging``).
"""
from access.db import RulesDB


def state_compatibility_rows(db: RulesDB) -> list:
    """Return all rows from the state_compatibility table."""
    return db.q("SELECT blocking_state_id, blocked_state_id, kind FROM state_compatibility")


def blocked_states(db: RulesDB, state_id: str) -> set[str]:
    """Return the set of state ids that *state_id* blocks (transitive closure)."""
    rows = db.q("SELECT blocked_state_id FROM state_compatibility "
                "WHERE blocking_state_id = ? AND kind = 'blocks'", state_id)
    result = {r["blocked_state_id"] for r in rows}
    changed = True
    while changed:
        changed = False
        for blocked in list(result):
            transitive = db.q("SELECT blocked_state_id FROM state_compatibility "
                              "WHERE blocking_state_id = ? AND kind = 'blocks'", blocked)
            for tr in transitive:
                if tr["blocked_state_id"] not in result:
                    result.add(tr["blocked_state_id"])
                    changed = True
    return result


def implied_states(db: RulesDB, state_id: str) -> set[str]:
    """Return the set of state ids that *state_id* implies (transitive closure)."""
    rows = db.q("SELECT blocked_state_id FROM state_compatibility "
                "WHERE blocking_state_id = ? AND kind = 'implies'", state_id)
    result = {r["blocked_state_id"] for r in rows}
    changed = True
    while changed:
        changed = False
        for implied in list(result):
            transitive = db.q("SELECT blocked_state_id FROM state_compatibility "
                              "WHERE blocking_state_id = ? AND kind = 'implies'", implied)
            for tr in transitive:
                if tr["blocked_state_id"] not in result:
                    result.add(tr["blocked_state_id"])
                    changed = True
    return result


def are_compatible(db: RulesDB, state_a: str, state_b: str) -> bool:
    """Return whether two states can coexist. Checks both directions for blocks."""
    a_blocks_b = db.scalar(
        "SELECT 1 FROM state_compatibility "
        "WHERE blocking_state_id = ? AND blocked_state_id = ? AND kind = 'blocks'",
        state_a, state_b)
    if a_blocks_b:
        return False
    b_blocks_a = db.scalar(
        "SELECT 1 FROM state_compatibility "
        "WHERE blocking_state_id = ? AND blocked_state_id = ? AND kind = 'blocks'",
        state_b, state_a)
    if b_blocks_a:
        return False
    return True
