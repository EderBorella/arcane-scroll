"""identity layer: size must be one the species allows; creature_type must match the species; unknown
species → silent. Synthetic, content-neutral rules."""
from validator.checks import identity
from validator.rules import Rules

R = Rules(species={
    "species-a": {"creature_type": "type-a", "sizes": ["small", "medium"], "speed": 30},
    "species-b": {"creature_type": "type-b", "sizes": ["medium"], "speed": 30},
})


def _sheet(species, size, ctype):
    return {"identity": {"species": species, "size": size, "creature_type": ctype}}


def _codes(s):
    return {v.code for v in identity.check(s, R)}


def test_legal_size_and_type():
    assert identity.check(_sheet("species-a", "small", "type-a"), R) == []


def test_choice_species_other_allowed_size_ok():
    assert identity.check(_sheet("species-a", "medium", "type-a"), R) == []


def test_illegal_size():                        # species-b only allows medium
    assert "illegal_size" in _codes(_sheet("species-b", "small", "type-b"))


def test_creature_type_mismatch():
    assert "creature_type_mismatch" in _codes(_sheet("species-a", "small", "type-x"))


def test_unknown_species_silent():
    assert identity.check(_sheet("species-zzz", "huge", "type-x"), R) == []


def test_absent_size_and_type_silent():         # nothing to compare when the fields are absent
    assert identity.check({"identity": {"species": "species-a"}}, R) == []
