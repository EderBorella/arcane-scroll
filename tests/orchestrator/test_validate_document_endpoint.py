"""T16 — the ``POST /validate-document`` orchestrator route (F07 D6).

Stateless: a ``character-document`` envelope -> the one folded ``completeness-report`` (validator
verdict + completeness manifest). Determinism against ``/v1/derive``: a document derived by that route
yields the identical report when POSTed here. Responses validate against the report contract.

Synthetic content-neutral ids only.
"""
import json
import pathlib

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"
_REPORT_VALIDATOR = Draft202012Validator(
    json.loads((_CONTRACTS / "completeness-report.schema.json").read_text()))

_MINIMAL_SPEC = {
    "species": "species-a",
    "background": "bg-a",
    "classes": [{"class": "class-a", "level": 3}],
    "subclasses": {"class-a": "sub-a"},
}


def _client(rules_db, monkeypatch):
    monkeypatch.setenv("ARCANE_RULES_DB", rules_db)
    from orchestrator.main import app
    return TestClient(app)


def test_validate_full_document_returns_report(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        doc = c.post("/v1/derive", json=_MINIMAL_SPEC).json()["document"]
        r = c.post("/validate-document", json=doc)
        assert r.status_code == 200, r.text
        report = r.json()
        assert list(_REPORT_VALIDATOR.iter_errors(report)) == []
        assert report["legal"] is True


def test_report_matches_the_derive_route(rules_db, monkeypatch):
    # A document from /v1/derive, re-validated here, yields the identical report — the shared helper.
    with _client(rules_db, monkeypatch) as c:
        derived = c.post("/v1/derive", json=_MINIMAL_SPEC).json()
        report = c.post("/validate-document", json=derived["document"]).json()
        assert report == derived["report"]


def test_partial_document_manifest_flags_missing_subclass(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        doc = c.post("/v1/derive", json=_MINIMAL_SPEC).json()["document"]
        doc["core"]["identity"]["classes"][0]["subclass"] = None
        report = c.post("/validate-document", json=doc).json()
        assert list(_REPORT_VALIDATOR.iter_errors(report)) == []
        keys = [e["choice_key"] for e in report["manifest"]]
        assert "core.classes.0.subclass" in keys
        assert report["awaiting_choices"] is True


def test_core_only_envelope_is_accepted(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        doc = c.post("/v1/derive", json=_MINIMAL_SPEC).json()["document"]
        report = c.post("/validate-document", json={"core": doc["core"]}).json()
        assert list(_REPORT_VALIDATOR.iter_errors(report)) == []
        assert report["legal"] is True


def test_shape_malformed_envelope_is_a_400(rules_db, monkeypatch):
    # A structurally-malformed sheet (a string where an object is expected) fails fast as a 400,
    # not a 500 — the controller maps ValueError/KeyError/TypeError.
    with _client(rules_db, monkeypatch) as c:
        r = c.post("/validate-document", json={"core": "not-an-object"})
        assert r.status_code == 400, r.text
