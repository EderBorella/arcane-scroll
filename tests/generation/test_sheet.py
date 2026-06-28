"""Character sheet generator: deterministic grammar + prompt assembly (no model)."""
from app.generation import sheet


def test_build_grammar_caster_structure(catalog):
    schema, fixed = sheet.build_grammar(catalog, "Human", [("mage", 5)], ["Evoker"])
    props = schema["properties"]
    assert {"name", "background", "alignment", "skill_choices", "spell_choices"} <= set(props)
    assert props["skill_choices"]["minItems"] == 2
    assert props["spell_choices"]["properties"]["cantrips"]["minItems"] == 4
    assert props["spell_choices"]["properties"]["spells"]["minItems"] == 8
    # enums come from the catalog
    assert props["background"]["enum"] == catalog.get("backgrounds")


def test_build_grammar_injects_fixed_fields(catalog):
    _, fixed = sheet.build_grammar(catalog, "Human", [("mage", 5)], ["Evoker"])
    assert fixed["race"] == "Human"
    assert fixed["classes"][0] == {"class": "Mage", "level": 5, "subclass": "Evoker"}
    assert sorted(fixed["ability_assignment"].values(), reverse=True) == [15, 14, 13, 12, 10, 8]


def test_build_grammar_noncaster_has_no_spells(catalog):
    schema, _ = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])
    assert "spell_choices" not in schema["properties"]


def test_build_grammar_omits_subclass_when_unresolved(catalog):
    _, fixed = sheet.build_grammar(catalog, "Human", [("mage", 1)], [None])
    assert "subclass" not in fixed["classes"][0]


def test_build_prompt(catalog):
    text = sheet.build_prompt(catalog, "Human", [("mage", 5)], ["Evoker"], unique="speaks in riddles")
    assert "TEST SYSTEM PROMPT" in text
    assert "mage 5 (Evoker)" in text
    assert "speaks in riddles" in text
