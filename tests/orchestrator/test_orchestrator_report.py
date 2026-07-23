"""The shared completeness-report composer (``orchestrator.report.compose_report``) — F07 D5/D6.

The one helper both document routes use: it runs the per-sheet validators over the present sheets,
folds them into one verdict, and adds the typed completeness manifest + ``awaiting_choices``. Its
response must validate against the ``completeness-report`` contract, it must reconstruct the manifest
from a document deterministically, and it must run only the validators for the sheets present.

Synthetic content-neutral ids only.
"""
import json
import pathlib

from jsonschema import Draft202012Validator

from engine.derivation.document import derive_document
from orchestrator.report import compose_report

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"
_REPORT_VALIDATOR = Draft202012Validator(json.loads((_CONTRACTS / "completeness-report.schema.json").read_text()))


def _full_choices():
    return {
        "character_id": "char-1",
        "character_name": "Test",
        "species": "species-a",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8},
        "background_increase": {"a1": 2, "a2": 1},
        "skills": ["sk1", "sk2"],
        "expertise": ["sk1"],
    }


def _envelope(doc):
    return {k: doc[k] for k in ("core", "inventory", "grimoire", "modifier", "companion") if k in doc}


def test_report_validates_against_contract(gen_access):
    doc = derive_document(_full_choices(), gen_access)
    report = compose_report(_envelope(doc), gen_access)
    assert list(_REPORT_VALIDATOR.iter_errors(report)) == []


def test_report_has_folded_verdict_shape(gen_access):
    doc = derive_document(_full_choices(), gen_access)
    report = compose_report(_envelope(doc), gen_access)
    assert set(report) >= {"legal", "complete", "awaiting_choices", "violations", "manifest", "summary"}
    assert isinstance(report["violations"], list)
    assert isinstance(report["manifest"], list)
    # summary is re-tallied from the folded findings.
    assert report["summary"]["total"] == len(report["violations"])
    assert report["summary"]["errors"] + report["summary"]["warnings"] == report["summary"]["total"]


def test_awaiting_choices_true_iff_required_manifest_entry(gen_access):
    doc = derive_document(_full_choices(), gen_access)
    report = compose_report(_envelope(doc), gen_access)
    expected = any(e["status"] == "required" for e in report["manifest"])
    assert report["awaiting_choices"] is expected


def test_partial_document_flags_missing_subclass(gen_access):
    doc = derive_document(_full_choices(), gen_access)
    env = _envelope(doc)
    # Strip the chosen subclass from the CORE identity — the manifest must flag it.
    env["core"]["identity"]["classes"][0]["subclass"] = None
    report = compose_report(env, gen_access)
    keys = [e["choice_key"] for e in report["manifest"]]
    assert "core.classes.0.subclass" in keys
    assert report["awaiting_choices"] is True


def test_core_only_envelope_runs_only_core(gen_access):
    doc = derive_document(_full_choices(), gen_access)
    report = compose_report({"core": doc["core"]}, gen_access)
    # A core-only envelope still yields a legal verdict (the other sheets are simply not run).
    assert list(_REPORT_VALIDATOR.iter_errors(report)) == []
    assert report["legal"] is True
