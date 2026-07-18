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
    # Base walk comes from the species (Species A, walk 30) with no speed grants — the
    # condition speed-penalty re-derivation is grounded in DB facts, not a hand-set speed.
    s["core"]["identity"] = {"size": "medium", "species": "Species A"}
    s["core"]["feats"] = []
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
    s["core"]["identity"] = {"size": "medium", "species": "Species A"}
    s["core"]["feats"] = []
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


# ── condition speed-penalty re-derivation over item + class speed bonuses (T132) ─
# The base-speed re-derivation is grounded in the species base walk, the owner
# speed grants (incl. magic items), and the class movement bonus — so the penalty
# is checked even on sheets that carry a speed item or a class speed bonus.


def _speed_sheet(cond_level, speed, *, species="Species A", classes=None,
                 equipped=None, item_states=None):
    """A conditioned sheet whose base speed comes from a species (+ optional class
    speed bonus and/or speed-granting item), NOT from a hand-set permanent_speed."""
    s = _sheet()
    ident = {"size": "medium", "species": species}
    if classes:
        ident["classes"] = classes
    s["core"]["identity"] = ident
    s["core"]["feats"] = []
    s["modifier"]["character_states"] = [
        {"state": "exhausted", "source": "environment",
         "source_type": "condition", "level": cond_level}]
    s["modifier"]["speed"] = speed
    if item_states is not None:
        s["modifier"]["item_states"] = item_states
    if equipped is not None:
        s["inventory"] = {"equipped": equipped, "backpack": []}
    return s


# 'Boots Alpha' is an attunement-required item granting fly 30 (sets_total).
_BOOTS = {"name": "Boots Alpha", "magic": True, "id": "boots1"}


def test_condition_speed_item_grant_wrong_speed_flagged(access):
    # exhaustion L1 (penalty 5): base walk 30, fly 30 (attuned boots) -> expected 25/25.
    # fly left unreduced at 30 must be flagged (the check used to skip item-speed sheets).
    s = _speed_sheet(1, {"walk": 25, "fly": 30}, equipped={"feet": _BOOTS},
                     item_states=[{"inventory_ref": "boots1", "attuned": True}])
    assert "condition-speed-mismatch" in _codes(s, access)


def test_condition_speed_item_grant_correct_speed_passes(access):
    s = _speed_sheet(1, {"walk": 25, "fly": 25}, equipped={"feet": _BOOTS},
                     item_states=[{"inventory_ref": "boots1", "attuned": True}])
    assert "condition-speed-mismatch" not in _codes(s, access)


def test_condition_speed_class_bonus_correct_speed_passes(access):
    # class-a level 6 grants a +15 speed bonus; species-a walk 30 -> base 45; L1 -> 40.
    s = _speed_sheet(1, {"walk": 40}, classes=[{"class": "Class A", "level": 6}])
    assert "condition-speed-mismatch" not in _codes(s, access)


def test_condition_speed_class_bonus_ignored_flagged(access):
    # 30 - 5 = 25 ignores the class speed bonus; the correct base is 45 -> 40, so 25 is wrong.
    s = _speed_sheet(1, {"walk": 25}, classes=[{"class": "Class A", "level": 6}])
    assert "condition-speed-mismatch" in _codes(s, access)
