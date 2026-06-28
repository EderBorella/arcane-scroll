"""Feature-choice descriptors (fighting style, expertise): gating, grammar props, and repair."""
from app.generation import features, sheet


def test_fighting_style_descriptor(catalog):
    ds = features.descriptors(catalog, [("fighter", 1, None)])
    fs = next(d for d in ds if d["field"] == "fighting_style")
    assert fs["enum"] == ["StyleA", "StyleB", "StyleC"] and fs["n"] == 1


def test_expertise_scales_with_level(catalog):
    n1 = next(d for d in features.descriptors(catalog, [("rogue", 1, None)]) if d["field"] == "expertise")["n"]
    n6 = next(d for d in features.descriptors(catalog, [("rogue", 6, None)]) if d["field"] == "expertise")["n"]
    assert (n1, n6) == (2, 4)                                   # 2 @L1, +2 @L6
    enum = next(d for d in features.descriptors(catalog, [("rogue", 1, None)]) if d["field"] == "expertise")["enum"]
    assert enum == ["Brawn", "Focus", "Menace", "Watch"]        # the class skill list


def test_no_features_for_plain_caster(catalog):
    assert features.descriptors(catalog, [("mage", 5, "Evoker")]) == []


def test_feature_props_shape(catalog):
    props, req = features.feature_props(catalog, [("fighter", 1, None)])
    assert "fighting_style" in req
    assert props["fighting_style"] == {"type": "array", "items": {"enum": ["StyleA", "StyleB", "StyleC"]},
                                       "minItems": 1, "maxItems": 1, "uniqueItems": True}


def test_repair_fighting_style_dedups_and_drops_invalid(catalog):
    ch = {"fighting_style": ["StyleA", "StyleA", "Bogus"]}
    features.repair_features(catalog, ch, [("fighter", 1, None)])
    assert ch["fighting_style"] == ["StyleA"]                   # deduped, invalid dropped, fit to n=1


def test_repair_expertise_is_subset_of_chosen_skills(catalog):
    ch = {"skill_choices": ["Brawn", "Menace", "Watch", "Focus"], "expertise": ["Brawn", "Bogus", "Brawn"]}
    features.repair_features(catalog, ch, [("rogue", 1, None)])
    assert len(ch["expertise"]) == 2 == len(set(ch["expertise"]))
    assert set(ch["expertise"]) <= set(ch["skill_choices"])     # only doubles chosen skills


def test_sheet_grammar_merges_feature_fields(catalog):
    fighter_props = sheet.build_grammar(catalog, "Human", [("fighter", 1)], [None])[0]["properties"]
    assert "fighting_style" in fighter_props
    rogue_props = sheet.build_grammar(catalog, "Human", [("rogue", 1)], [None])[0]["properties"]
    assert "expertise" in rogue_props and "fighting_style" not in rogue_props
