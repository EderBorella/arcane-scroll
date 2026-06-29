"""Features & traits: class features by level, race traits, background feature."""
from app.derivation import features


def test_class_features_by_level(catalog):
    feats = features.features_and_traits(catalog, {"race": "Human", "classes": [{"class": "Mage", "level": 2}]})
    names = [f["name"] for f in feats]
    assert "Spellcasting" in names and "Arcane Recovery" in names


def test_features_capped_by_level(catalog):
    names = [f["name"] for f in
             features.features_and_traits(catalog, {"race": "Human", "classes": [{"class": "Mage", "level": 1}]})]
    assert "Spellcasting" in names and "Arcane Recovery" not in names      # L2 feature not yet granted


def test_race_traits_and_background_feature(catalog):
    feats = features.features_and_traits(catalog, {"race": "Human", "background": "Scholar",
                                                   "classes": [{"class": "Mage", "level": 1}]})
    by_source = {f["name"]: f["source"] for f in feats}
    assert by_source.get("Versatile") == "Race"
    assert by_source.get("Bookish") == "Background"


def test_subrace_traits_include_racial_traits_and_parent(catalog):
    feats = features.features_and_traits(catalog, {"race": "Highlander", "classes": [{"class": "Mage", "level": 1}]})
    names = [f["name"] for f in feats]
    assert "Sure-Footed" in names      # subrace's own racial_traits
    assert "Versatile" in names        # inherited from the parent (Human) traits
