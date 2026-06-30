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


def test_predecide_picks_background_and_fighting_style(catalog):
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "fighter", "level": 3}]})
    pre = sheet.predecide(catalog, spec, [("fighter", 3, None)], random.Random(0))
    assert pre["background"] in catalog.get("backgrounds")
    assert pre["fighting_style"] in ["StyleA", "StyleB", "StyleC"]
    # explicit background wins; a non-granting class gets no fighting style
    spec2 = request.parse(catalog, {"race": "Human", "classes": [{"class": "mage", "level": 5}], "background": "Scholar"})
    pre2 = sheet.predecide(catalog, spec2, [("mage", 5, None)], random.Random(0))
    assert pre2["background"] == "Scholar" and "fighting_style" not in pre2


def test_build_grammar_excludes_predecided_fields(catalog):
    # pre-decided fields are injected as fixed and removed from the model's contract
    schema, fixed = sheet.build_grammar(catalog, "Human", [("fighter", 3)], [None],
                                        predecided={"background": "Scholar", "fighting_style": "StyleA"})
    props = schema["properties"]
    assert "background" not in props and "fighting_style" not in props
    assert fixed["background"] == "Scholar" and fixed["fighting_style"] == "StyleA"
    # without predecided (direct call), background stays a model field
    assert "background" in sheet.build_grammar(catalog, "Human", [("fighter", 3)], [None])[0]["properties"]


def test_build_grammar_noncaster_has_no_spells(catalog):
    schema, _ = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])
    assert "spell_choices" not in schema["properties"]


def test_build_grammar_omits_subclass_when_unresolved(catalog):
    _, fixed = sheet.build_grammar(catalog, "Human", [("mage", 1)], [None])
    assert "subclass" not in fixed["classes"][0]


def test_build_grammar_excludes_equipment_pass1(catalog):
    # pass 1 carries everything but equipment (equipment is the second pass)
    schema, fixed = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])
    assert not any(k.startswith("equipment") for k in schema["properties"])
    assert "roll_starting_wealth" not in fixed          # the flag is stamped in generate(), not here


def test_build_equipment_grammar_pass2(catalog):
    schema, req = sheet.build_equipment_grammar(catalog, [("warrior", 3)])
    assert {"equipment_0", "equipment_1"} <= set(schema["properties"]) and set(req) == {"equipment_0", "equipment_1"}
    # a class with no equipment slots → empty pass-2 grammar (the orchestrator then skips the call)
    assert sheet.build_equipment_grammar(catalog, [("mage", 5)])[1] == []


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


def test_generate_two_pass_equipment(catalog, monkeypatch):
    # pass 1 builds the sheet; pass 2 (equipment grammar) picks gear fitted to that build
    import app.generation.client as model_client
    schemas = []

    def fake(prompt, schema, **kw):
        schemas.append(schema)
        if "equipment_1" in schema["properties"]:        # pass 2 — equipment grammar
            return {"equipment_0": "WeaponA",
                    "equipment_1": {"route": "a martial weapon", "weapons": ["MartialA"]}}
        return {"name": "W", "background": "Scholar", "alignment": "Order",   # pass 1 — the sheet
                "skill_choices": ["Brawn", "Menace"]}

    monkeypatch.setattr(model_client, "generate", fake)
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "warrior", "level": 3}]})
    ch = sheet.generate(catalog, spec, rng=random.Random(0))
    assert len(schemas) == 2                              # two model passes
    assert ch["equipment_0"] == "WeaponA" and ch["equipment_1"]["route"] == "a martial weapon"
    assert ch["roll_starting_wealth"] is False


def test_generate_skips_pass2_when_rolling_wealth(catalog, monkeypatch):
    import app.generation.client as model_client
    schemas = []

    def fake(prompt, schema, **kw):
        schemas.append(schema)
        return {"name": "W", "background": "Scholar", "alignment": "Order", "skill_choices": ["Brawn", "Menace"]}

    monkeypatch.setattr(model_client, "generate", fake)
    spec = request.parse(catalog, {"race": "Human", "classes": [{"class": "warrior", "level": 3}],
                                   "roll_starting_wealth": True})
    ch = sheet.generate(catalog, spec, rng=random.Random(0))
    assert len(schemas) == 1                              # no equipment pass
    assert not any(k.startswith("equipment") for k in ch) and ch["roll_starting_wealth"] is True


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
