"""Backstory generator: schema bounds/enums, prompt assembly (unique vs archetype), physical
clamping, and the orchestrator (model mocked). Flavour data is served from the reference DB via the
generator access layer; the request carries a species id."""
import random

from app.generation import backstory, helpers as H


def test_build_schema_bounds_and_enums(gen_access):
    p = backstory.build_schema(gen_access, "species-a")["properties"]
    assert (p["age"]["minimum"], p["age"]["maximum"]) == (16, 90)
    assert p["gender"]["enum"] == ["Male", "Female", "Nonbinary"]
    assert p["skin"]["enum"] == ["Pale", "Tan", "Dark"]              # species-a → default palette
    assert p["personality_traits"]["minItems"] == 2
    assert {"age", "height_inches", "weight_lbs", "gender", "eyes", "hair", "skin",
            "personality_traits", "ideal", "bond", "flaw", "backstory"} == set(p)


def test_build_schema_species_skin_override(gen_access):
    # species-v overrides the skin palette; other axes still use the default
    p = backstory.build_schema(gen_access, "species-v")["properties"]
    assert p["skin"]["enum"] == ["Bronze", "Silver"]
    assert p["gender"]["enum"] == ["Male", "Female", "Nonbinary"]


def test_build_schema_default_bounds_for_unknown_species(gen_access):
    # species-l has no bounds row → generic fallback
    p = backstory.build_schema(gen_access, "species-l")["properties"]
    assert p["age"]["minimum"] == 16 and p["age"]["maximum"] == 100


def test_build_prompt_uses_unique_hint(gen_access):
    ch = {"species": "species-a", "classes": [{"class": "class-a", "level": 5}], "name": "X"}
    txt = backstory.build_prompt(gen_access, ch, "species-a", "Species A",
                                 unique="collects every left shoe")
    assert "TEST FLAVOUR PROMPT" in txt
    assert "collects every left shoe" in txt
    assert "Physical limits for a Species A" in txt


def test_build_prompt_uses_archetype_when_no_unique(gen_access):
    ch = {"species": "species-a", "classes": [{"class": "class-a", "level": 5}]}
    txt = backstory.build_prompt(gen_access, ch, "species-a", "Species A",
                                 archetype="follow a mundane trade")
    assert "Story angle to follow: follow a mundane trade" in txt


def test_clamp_physical(gen_access):
    fl = {"age": 5000, "height_inches": 999, "weight_lbs": 1}
    H.clamp_physical(gen_access, "species-a", fl)
    assert fl == {"age": 90, "height_inches": 78, "weight_lbs": 110}


def test_generate_injects_archetype_and_clamps(gen_access, monkeypatch):
    import app.generation.client as model_client
    captured = {}

    def fake(prompt, schema, **kw):
        captured["prompt"] = prompt
        return {"age": 9999, "height_inches": 70, "weight_lbs": 150, "gender": "Male",
                "eyes": "Brown", "hair": "Black", "skin": "Pale",
                "personality_traits": ["calm", "wry"], "ideal": "truth", "bond": "home",
                "flaw": "proud", "backstory": "Once, in a quiet town..."}

    monkeypatch.setattr(model_client, "generate", fake)
    out = backstory.generate(gen_access,
                             {"species": "species-a", "classes": [{"class": "class-a", "level": 5}]},
                             rng=random.Random(0))
    assert out["age"] == 90                                  # clamped into range
    assert "Story angle to follow:" in captured["prompt"]    # no 'unique' → archetype injected
    assert "Species A" in captured["prompt"]                 # species id resolved to display name


def test_generate_uses_unique_over_archetype(gen_access, monkeypatch):
    import app.generation.client as model_client
    captured = {}
    monkeypatch.setattr(model_client, "generate",
                        lambda prompt, schema, **kw: captured.update(prompt=prompt) or
                        {"age": 40, "height_inches": 70, "weight_lbs": 150, "gender": "Male",
                         "eyes": "Blue", "hair": "Brown", "skin": "Tan",
                         "personality_traits": ["a", "b"], "ideal": "i", "bond": "b",
                         "flaw": "f", "backstory": "tale"})
    backstory.generate(gen_access, {"species": "species-a",
                                    "classes": [{"class": "class-a", "level": 5}],
                                    "unique": "afraid of mirrors"}, rng=random.Random(0))
    assert "afraid of mirrors" in captured["prompt"]
    assert "Story angle to follow:" not in captured["prompt"]
