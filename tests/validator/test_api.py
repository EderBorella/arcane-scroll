"""HTTP wiring for the validator service: /health, /ready, and POST /validate returning the full
report. Uses a synthetic rules dir written to a temp path."""
import json

from fastapi.testclient import TestClient


def _rules_dir(tmp_path):
    (tmp_path / "class_progression.json").write_text(json.dumps(
        {"alpha": {"1": {"proficiency_bonus": 2, "features": ["Spellcasting"]},
                   "3": {"proficiency_bonus": 2, "features": ["Alpha Subclass"]}}}))
    (tmp_path / "backgrounds.json").write_text(json.dumps({"scholar": {"abilities": ["int", "wis", "cha"]}}))
    (tmp_path / "spell_lists.json").write_text(json.dumps({"caster-a": {"Spell-A": 1}}))
    return tmp_path


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIDATOR_DATA", str(_rules_dir(tmp_path)))
    from validator.main import app
    return TestClient(app)


def test_health_and_ready(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/health").json() == {"status": "ok"}
        ready = c.get("/ready").json()
        assert ready["ready"] is True and ready["rules"]["classes"] == 1


def test_validate_returns_full_report(tmp_path, monkeypatch):
    sheet = {"proficiency_bonus": 2,
             "identity": {"total_level": 1, "background": "Scholar",
                          "classes": [{"class": "Alpha", "level": 1, "subclass": "Sub"}]},
             "abilities": {a: {"base": 10, "racial_bonus": 0, "final": 10, "modifier": 0}
                           for a in ("str", "dex", "con", "int", "wis", "cha")}}
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/validate", json=sheet)
        assert r.status_code == 200
        body = r.json()
        assert {"legal", "complete", "violations", "summary"} <= set(body)
        codes = {v["code"] for v in body["violations"]}
        assert "subclass_too_early" in codes and body["legal"] is False   # subclass @1 unlocks @3
