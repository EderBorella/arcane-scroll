"""movement layer: with speed_detail present, base matches the species, base_mode is a real key, the
speeds map re-derives from the detail (incl. a relative mode), and modifier sources exist on the
character. No speed_detail → silent. Synthetic, content-neutral rules."""
from validator.checks import movement
from validator.rules import Rules

R = Rules(species={"species-a": {"creature_type": "type-a", "sizes": ["medium"], "speed": 30}})

_DETAIL = {"base": 30, "base_source": "species-a", "base_mode": "mode-a",
           "modifiers": [{"mode": "mode-a", "value": 5, "source": "feat-a"},
                         {"mode": "mode-b", "relative": {"of": "mode-a", "factor": 1}, "source": "feature-a"}]}


def _sheet(speed, detail, feats=("feat-a",), features=("feature-a",)):
    return {"identity": {"species": "species-a"},
            "feats": [{"name": n} for n in feats],
            "features": [{"name": n} for n in features],
            "combat": {"speed": speed, "speed_detail": detail}}


def _codes(s):
    return {v.code for v in movement.check(s, R)}


def test_legal_speed_derives():                 # mode-a: 30+5=35 ; mode-b: 1×35=35
    assert movement.check(_sheet({"mode-a": 35, "mode-b": 35}, _DETAIL), R) == []


def test_no_detail_silent():
    assert movement.check({"identity": {"species": "species-a"}, "combat": {"speed": {"mode-a": 99}}}, R) == []


def test_base_speed_mismatch():                 # base 25 ≠ species 30 (map matched to 25-derivation)
    assert "base_speed_mismatch" in _codes(_sheet({"mode-a": 30, "mode-b": 30}, dict(_DETAIL, base=25)))


def test_speed_not_derivable():                 # map says 99 but detail derives 35
    assert "speed_not_derivable" in _codes(_sheet({"mode-a": 99, "mode-b": 35}, _DETAIL))


def test_base_mode_absent():
    assert "base_mode_absent" in _codes(_sheet({"mode-a": 35, "mode-b": 35}, dict(_DETAIL, base_mode="mode-z")))


def test_unknown_source_warns():                # feat-a/feature-a not on the character
    assert "speed_source_unknown" in _codes(_sheet({"mode-a": 35, "mode-b": 35}, _DETAIL, feats=(), features=()))
