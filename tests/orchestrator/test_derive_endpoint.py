"""T15 — the ``POST /v1/derive`` orchestrator route (F07 D5).

Stateless, deterministic, NO-model derive: a minimal build spec -> a ``character-document`` envelope
plus a ``completeness-report``. Fundamentals missing -> HTTP 400 (fail-fast). Same input -> same
output. Responses validate against the D1 contracts.

Synthetic content-neutral ids only.
"""
import json
import pathlib

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"


def _schema(name):
    return json.loads((_CONTRACTS / name).read_text())


_SHEETS = [_schema(n) for n in ("core-sheet.schema.json", "inventory.schema.json",
                                "grimoire.schema.json", "modifier-sheet.schema.json",
                                "companion-modifier.schema.json")]
_ENVELOPE = _schema("character-document.schema.json")
_REGISTRY = Registry().with_resources([(s["$id"], Resource.from_contents(s))
                                       for s in (_SHEETS + [_ENVELOPE])])
_ENVELOPE_VALIDATOR = Draft202012Validator(_ENVELOPE, registry=_REGISTRY)
_REPORT_VALIDATOR = Draft202012Validator(_schema("completeness-report.schema.json"))

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


def test_derive_minimal_core_returns_document_and_report(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        r = c.post("/v1/derive", json=_MINIMAL_SPEC)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"document", "report"}
        doc = body["document"]
        assert {"core", "inventory", "modifier"} <= set(doc)
        # Responses validate against the D1 contracts.
        assert list(_ENVELOPE_VALIDATOR.iter_errors(doc)) == []
        assert list(_REPORT_VALIDATOR.iter_errors(body["report"])) == []


def test_derive_fails_fast_on_missing_fundamental(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        # No species — a missing fundamental must fail fast with a 4xx, not derive a partial document.
        r = c.post("/v1/derive", json={"classes": [{"class": "class-a", "level": 3}]})
        assert r.status_code == 400
        # An unknown class id is equally rejected.
        r2 = c.post("/v1/derive", json={"species": "species-a", "classes": [{"class": "nope", "level": 3}]})
        assert r2.status_code == 400


def test_derive_is_deterministic(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        a = c.post("/v1/derive", json=_MINIMAL_SPEC).json()
        b = c.post("/v1/derive", json=_MINIMAL_SPEC).json()
        assert a == b


def test_derive_without_subclass_flags_it_in_manifest(rules_db, monkeypatch):
    with _client(rules_db, monkeypatch) as c:
        spec = {k: v for k, v in _MINIMAL_SPEC.items() if k != "subclasses"}
        body = c.post("/v1/derive", json=spec).json()
        keys = [e["choice_key"] for e in body["report"]["manifest"]]
        assert "core.classes.0.subclass" in keys
        assert body["report"]["awaiting_choices"] is True
