from fastapi.testclient import TestClient


def test_validate_endpoint_returns_report(rules_db, monkeypatch):
    monkeypatch.setenv("ARCANE_RULES_DB", rules_db)
    from validator.main import app
    with TestClient(app) as client:
        clean_abilities = {
            "x1": {"base": 13, "background_bonus": 2, "final": 15, "modifier": 2},
            "x2": {"base": 13, "background_bonus": 1, "final": 14, "modifier": 2},
            "x3": {"base": 13, "final": 13, "modifier": 1},
            "x4": {"base": 13, "final": 13, "modifier": 1},
            "x5": {"base": 13, "final": 13, "modifier": 1},
            "x6": {"base": 13, "final": 13, "modifier": 1},
        }
        good = {"identity": {"species": "Species A", "size": "Size A", "creature_type": "Type A",
                             "background": "Background A", "total_level": 3, "xp": 900,
                             "classes": [{"class": "Class A", "subclass": "Sub A", "level": 3}]},
                "abilities": clean_abilities}
        r = client.post("/validate", json=good)
        assert r.status_code == 200
        body = r.json()
        assert body["legal"] is True
        bad = {"identity": dict(good["identity"], total_level=5), "abilities": clean_abilities}
        assert client.post("/validate", json=bad).json()["legal"] is False
