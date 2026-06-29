"""Controller (HTTP): /v1/characters end-to-end with the model client mocked. Exercises the wiring
(catalog singleton via lifespan, request validation, generator orchestration), not the model."""
import pytest
from fastapi.testclient import TestClient


def _fake_sheet():
    # valid response for the synthetic mage-5 grammar (4 cantrips, 8 spells)
    return {
        "name": "Tester", "background": "Scholar", "alignment": "Balance",
        "skill_choices": ["Lore", "Runes"], "feat": "FeatC",   # mage L5 grants one feat slot
        "spell_choices": {"cantrips": ["Spark", "Glimmer", "Whisper", "Flicker"],
                          "spells": ["Bolt", "Ward", "Mist", "Veil", "Quake", "Gale", "Snare", "Ember"]},
    }


def _fake_flavour():
    return {"age": 40, "height_inches": 70, "weight_lbs": 150, "gender": "Male",
            "eyes": "Brown", "hair": "Black", "skin": "Pale",
            "personality_traits": ["calm", "wry"], "ideal": "truth", "bond": "home",
            "flaw": "proud", "backstory": "A short tale."}


def _fake_model(prompt, schema, **kw):
    # one mock for both endpoints — pick the shape from the requested schema
    return _fake_flavour() if "backstory" in schema.get("properties", {}) else _fake_sheet()


@pytest.fixture
def client(db_path, monkeypatch):
    import app.generation.client as model_client
    monkeypatch.setattr(model_client, "generate", _fake_model)
    from app.main import app
    with TestClient(app) as c:        # lifespan loads the synthetic catalog from ARCANE_DB_PATH
        yield c


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready").json()
    assert ready["ready"] is True and ready["records_total"] > 0


def test_post_characters_ok(client):
    r = client.post("/v1/characters", json={"race": "Human", "classes": [{"class": "mage", "level": 5}]})
    assert r.status_code == 200
    body = r.json()
    ch = body["choices"]
    assert ch["race"] == "Human"
    assert ch["classes"][0]["class"] == "Mage"          # code-injected fixed field
    assert ch["ability_assignment"]["int"] == 15        # deterministic assignment
    assert len(ch["skill_choices"]) == 2
    assert len(ch["spell_choices"]["spells"]) == 8
    # the {choices, sheet} contract: derivation runs through the endpoint
    sheet = body["sheet"]
    assert sheet["level"] == 5 and sheet["proficiency_bonus"] == 3
    assert sheet["ability_scores"]["int"] == 16         # 15 + human racial
    assert sheet["spellcasting"]["Mage"]["save_dc"] > 8 and sheet["max_hp"] > 0


def test_post_characters_bad_race_400(client):
    r = client.post("/v1/characters", json={"race": "Orc", "classes": [{"class": "mage", "level": 1}]})
    assert r.status_code == 400
    assert "race" in r.json()["detail"].lower()


def test_post_characters_illegal_multiclass_400(client):
    # warrior(str,con) + oracle(wis,cha) = 4 abilities need 13+ — rejected at the endpoint
    r = client.post("/v1/characters", json={"race": "Human",
                    "classes": [{"class": "warrior", "level": 3}, {"class": "oracle", "level": 2}]})
    assert r.status_code == 400 and "multiclass" in r.json()["detail"].lower()


def test_post_backstory_ok(client):
    r = client.post("/v1/backstory", json={"character": {"race": "Human",
                    "classes": [{"class": "Mage", "level": 5}], "name": "Tester"}})
    assert r.status_code == 200
    fl = r.json()["flavour"]
    assert fl["backstory"] and len(fl["personality_traits"]) == 2
    assert 16 <= fl["age"] <= 90          # within the race bounds


def test_post_backstory_missing_fields_400(client):
    r = client.post("/v1/backstory", json={"character": {"name": "Nameless"}})
    assert r.status_code == 400
