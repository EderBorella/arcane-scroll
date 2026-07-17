"""Tests for the MODIFIER validator's independent re-derivation of condition effects
(read from condition_effect, not from the deriver): speed-zero, per-level exhaustion
speed/D20 penalties, resistance to all damage, and condition immunities."""
from tests.validator.test_modifier_check import _sheet


def _codes(sheet, access):
    from validator.checks.modifier import check
    return {v.code for v in check(sheet, access)}


def _with_state(state_id, level=None, **mod):
    st = {"state": state_id, "source": "environment", "source_type": "condition"}
    if level is not None:
        st["level"] = level
    s = _sheet()
    s["core"]["permanent_speed"] = {"walk": 30}
    s["modifier"]["character_states"] = [st]
    for k, val in mod.items():
        s["modifier"][k] = val
    return s


# ── speed-zero (grappled / restrained) ────────────────────────────────────────


def test_grappled_speed_zero_passes(access):
    s = _with_state("grappled", speed={"walk": 0})
    assert "condition-speed-not-zero" not in _codes(s, access)


def test_grappled_nonzero_speed_flagged(access):
    s = _with_state("grappled", speed={"walk": 30})
    assert "condition-speed-not-zero" in _codes(s, access)


# ── exhaustion: per-level speed + D20 penalty ─────────────────────────────────


def test_exhaustion_correct_penalties_pass(access):
    s = _with_state("exhausted", level=3, speed={"walk": 15}, d20_penalty=6)
    codes = _codes(s, access)
    assert "condition-d20-penalty-mismatch" not in codes
    assert "condition-speed-mismatch" not in codes


def test_exhaustion_missing_d20_penalty_flagged(access):
    s = _with_state("exhausted", level=3, speed={"walk": 15})  # no d20_penalty
    assert "condition-d20-penalty-mismatch" in _codes(s, access)


def test_exhaustion_unreduced_speed_flagged(access):
    s = _with_state("exhausted", level=3, speed={"walk": 30}, d20_penalty=6)
    assert "condition-speed-mismatch" in _codes(s, access)


# ── petrified: resistance to all damage + poisoned-condition immunity ──────────


def _petrified(resistances, condition_immunities):
    s = _sheet()
    s["core"]["permanent_speed"] = {"walk": 30}
    s["modifier"]["character_states"] = [
        {"state": "petrified", "source": "environment", "source_type": "condition"}]
    s["modifier"]["speed"] = {"walk": 0}
    s["modifier"]["effective_defenses"] = {
        "resistances": resistances, "immunities": [], "vulnerabilities": [],
        "condition_immunities": condition_immunities, "save_advantages": [],
        "condition_advantages": [],
    }
    return s


def test_petrified_full_defenses_pass(access):
    from access.validator import defenses as defenses_q
    all_types = sorted(defenses_q.damage_type_ids(access))
    s = _petrified(all_types, ["poisoned"])
    codes = _codes(s, access)
    assert "condition-resistance-missing" not in codes
    assert "condition-immunity-missing" not in codes


def test_petrified_missing_resistance_flagged(access):
    s = _petrified(["fire"], ["poisoned"])
    assert "condition-resistance-missing" in _codes(s, access)


def test_petrified_missing_condition_immunity_flagged(access):
    from access.validator import defenses as defenses_q
    all_types = sorted(defenses_q.damage_type_ids(access))
    s = _petrified(all_types, [])
    assert "condition-immunity-missing" in _codes(s, access)
