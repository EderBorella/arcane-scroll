"""Request parsing/validation against the catalog."""
import pytest

from app.generation import request


def test_parse_valid(catalog):
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 5}]})
    assert spec.race == "Human"
    assert spec.classes == [("mage", 5)]
    assert spec.subclasses == {} and spec.unique is None


def test_parse_roll_starting_wealth_flag(catalog):
    on = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 1}],
                                 "roll_starting_wealth": True})
    assert on.roll_wealth is True
    off = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 1}]})
    assert off.roll_wealth is False


def test_parse_canonicalises_background(catalog):
    assert request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 1}],
                                   "background": "scholar"}).background == "Scholar"


def test_parse_unknown_background_raises(catalog):
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 1}],
                                "background": "Nope"})


def test_parse_canonicalises_race_casing(catalog):
    # a case-insensitively-valid race resolves to the catalog's display name, so downstream
    # flavour lookups (keyed by display name) don't silently fall back to generic bounds
    assert request.parse(catalog, {"race": "HUMAN", "classes": [{"class": "mage", "level": 1}]}).race == "Human"
    assert request.parse(catalog, {"race": "human", "classes": [{"class": "mage", "level": 1}]}).race == "Human"


def test_parse_carries_options(catalog):
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 3}],
                                   "subclasses": {"mage": "Evoker"}, "unique": "collects teeth"})
    assert spec.subclasses == {"mage": "Evoker"}
    assert spec.unique == "collects teeth"


def test_parse_unknown_race(catalog):
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Orc", "classes": [{"class": "mage", "level": 1}]})


def test_parse_unknown_class(catalog):
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Human", "classes": [{"class": "bard", "level": 1}]})


def test_parse_level_out_of_range(catalog):
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 0}]})


def test_parse_no_classes(catalog):
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Human", "classes": []})


def test_parse_multiclass(catalog):
    spec = request.parse(catalog, {"race": "Human",
                                   "classes": [{"class": "mage", "level": 3}, {"class": "oracle", "level": 2}]})
    assert spec.classes == [("mage", 3), ("oracle", 2)]      # mage(int) + oracle(wis,cha) = 3 abilities, legal


def test_parse_rejects_illegal_multiclass(catalog):
    # warrior(str,con) + oracle(wis,cha) = 4 abilities need 13+ — impossible under the standard array
    with pytest.raises(ValueError):
        request.parse(catalog, {"race": "Human",
                                "classes": [{"class": "warrior", "level": 3}, {"class": "oracle", "level": 2}]})
