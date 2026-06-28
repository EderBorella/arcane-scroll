"""Controller (HTTP): /v1/characters end-to-end with the model client mocked. Exercises the wiring
(catalog singleton via lifespan, request validation, generator orchestration), not the model."""
import pytest
from fastapi.testclient import TestClient


def _fake_model_output():
    # a valid response for the synthetic mage-5 grammar (4 cantrips, 8 spells)
    return {
        "name": "Tester", "background": "Scholar", "alignment": "Balance",
        "skill_choices": ["Lore", "Runes"],
        "spell_choices": {"cantrips": ["Spark", "Glimmer", "Whisper", "Flicker"],
                          "spells": ["Bolt", "Ward", "Mist", "Veil", "Quake", "Gale", "Snare", "Ember"]},
    }


@pytest.fixture
def client(db_path, monkeypatch):
    import app.generation.client as model_client
    monkeypatch.setattr(model_client, "generate", lambda prompt, schema, **kw: _fake_model_output())
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
    ch = r.json()["choices"]
    assert ch["race"] == "Human"
    assert ch["classes"][0]["class"] == "Mage"          # code-injected fixed field
    assert ch["ability_assignment"]["int"] == 15        # deterministic assignment
    assert len(ch["skill_choices"]) == 2
    assert len(ch["spell_choices"]["spells"]) == 8


def test_post_characters_bad_race_400(client):
    r = client.post("/v1/characters", json={"race": "Orc", "classes": [{"class": "mage", "level": 1}]})
    assert r.status_code == 400
    assert "race" in r.json()["detail"].lower()
