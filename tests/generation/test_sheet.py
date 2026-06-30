"""Character sheet generator: deterministic grammar + prompt assembly, and the orchestrator."""
import random

from app.generation import request, sheet


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


def test_build_grammar_roll_wealth_omits_equipment(catalog):
    # taking gold instead of equipment drops the equipment slots and flags the choice
    schema, fixed = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"], roll_wealth=True)
    assert not any(k.startswith("equipment") for k in schema["properties"])
    assert fixed["roll_starting_wealth"] is True
    # default keeps equipment and flags false
    schema2, fixed2 = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])
    assert "equipment_0" in schema2["properties"] and fixed2["roll_starting_wealth"] is False


def test_build_prompt(catalog):
    text = sheet.build_prompt(catalog, "Human", [("mage", 5)], ["Evoker"], unique="speaks in riddles")
    assert "TEST SYSTEM PROMPT" in text
    assert "mage 5 (Evoker)" in text
    assert "speaks in riddles" in text


def test_build_grammar_multiclass(catalog):
    schema, fixed = sheet.build_grammar(catalog, "Human", [("mage", 3), ("oracle", 3)], ["Evoker", "Seer"])
    sp = schema["properties"]["spell_choices"]["properties"]
    assert sp["cantrips"]["minItems"] == 5 and sp["spells"]["minItems"] == 7   # combined pools/counts
    assert len(fixed["classes"]) == 2
    assert fixed["classes"][1] == {"class": "Oracle", "level": 3, "subclass": "Seer"}


def test_generate_orchestrator_merges_fixed_and_repairs(catalog, monkeypatch):
    import app.generation.client as model_client

    def fake(prompt, schema, **kw):     # model returns dups; repair must clean to the granted counts
        return {"name": "X", "background": "Scholar", "alignment": "Order",
                "skill_choices": ["Lore", "Lore"],
                "spell_choices": {"cantrips": ["Spark", "Spark", "Glimmer", "Whisper"],
                                  "spells": ["Bolt", "Bolt", "Ward", "Mist", "Veil", "Quake", "Gale", "Snare"]}}

    monkeypatch.setattr(model_client, "generate", fake)
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 5}]})
    ch = sheet.generate(catalog, spec, rng=random.Random(0))
    assert ch["race"] == "Human" and ch["classes"][0]["class"] == "Mage"   # fixed fields merged in
    assert ch["ability_assignment"]["int"] == 15
    assert len(ch["skill_choices"]) == 2 == len(set(ch["skill_choices"]))  # repaired
    assert len(ch["spell_choices"]["cantrips"]) == 4 == len(set(ch["spell_choices"]["cantrips"]))
    assert len(ch["spell_choices"]["spells"]) == 8 == len(set(ch["spell_choices"]["spells"]))
