"""Request parsing/validation against the catalog."""
import pytest

from app.generation import request


def test_parse_valid(catalog):
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 5}]})
    assert spec.race == "Human"
    assert spec.classes == [("mage", 5)]
    assert spec.subclasses == {} and spec.unique is None


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
    assert spec.classes == [("mage", 3), ("oracle", 2)]
