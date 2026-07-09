"""Tests for the state_compatibility access layer (B9)."""
from access.validator.state_compatibility import (
    state_compatibility_rows, blocked_states, implied_states, are_compatible,
)


class TestStateCompatibility:
    def test_14_rows_exist(self, access):
        rows = state_compatibility_rows(access.db)
        assert len(rows) == 14, f"expected 14, got {len(rows)}"

    def test_blocks_and_implies_are_present(self, access):
        rows = state_compatibility_rows(access.db)
        kinds = {r["kind"] for r in rows}
        assert kinds == {"blocks", "implies"}

    def test_incapacitated_blocks_raging(self, access):
        assert not are_compatible(access.db, "incapacitated", "raging")
        assert not are_compatible(access.db, "raging", "incapacitated")

    def test_raging_blocks_concentrating(self, access):
        assert not are_compatible(access.db, "raging", "concentrating")

    def test_unconscious_implies_incapacitated(self, access):
        implied = implied_states(access.db, "unconscious")
        assert "incapacitated" in implied
        assert "prone" in implied

    def test_petrified_implies_incapacitated(self, access):
        implied = implied_states(access.db, "petrified")
        assert "incapacitated" in implied

    def test_compatible_states_are_independent(self, access):
        assert are_compatible(access.db, "raging", "hasted")
        assert are_compatible(access.db, "hasted", "blessed")

    def test_unknown_state_has_no_blocks(self, access):
        assert are_compatible(access.db, "unknown_state", "raging")
        assert blocked_states(access.db, "unknown_state") == set()
