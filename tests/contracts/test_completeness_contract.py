"""Contract tests for the F07 orchestrator contracts (Deliverable D1, light v1):
the ``character-document`` envelope and the ``completeness-report``.

Schema-only: these validate the JSON Schema contracts themselves — the envelope's
shape and cross-sheet $refs, and the report's typed manifest. No runtime
derive/validate behaviour is exercised; that arrives with later F07 deliverables.

Content-neutral: synthetic ids only (``class-a``, ``species-a`` …) from the shared
rules-DB fixture.
"""
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from engine.derivation.document import derive_document

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"


def _schema(name):
    return json.loads((_CONTRACTS / name).read_text())


_SHEETS = [
    _schema(n)
    for n in (
        "core-sheet.schema.json",
        "inventory.schema.json",
        "grimoire.schema.json",
        "modifier-sheet.schema.json",
        "companion-modifier.schema.json",
    )
]
_ENVELOPE = _schema("character-document.schema.json")
_REPORT = _schema("completeness-report.schema.json")

# Registry so the envelope's external $refs to each sheet URN resolve.
_REGISTRY = Registry().with_resources(
    [(s["$id"], Resource.from_contents(s)) for s in (_SHEETS + [_ENVELOPE])]
)
_ENVELOPE_VALIDATOR = Draft202012Validator(_ENVELOPE, registry=_REGISTRY)
_REPORT_VALIDATOR = Draft202012Validator(_REPORT)


def _core_choices():
    """A single-class level-3 build with a subclass (mirrors the derivation fixtures)."""
    return {
        "character_id": "char-1",
        "character_name": "Test Character",
        "species": "species-a",
        "size": "size-a",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {
            "a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8, "wisdom": 10,
        },
        "background_increase": {"a1": 2, "a2": 1},
        "skills": ["sk1", "sk2"],
        "feats": [],
        "languages": [],
    }


class TestSchemasThemselves:
    def test_envelope_schema_is_valid(self):
        Draft202012Validator.check_schema(_ENVELOPE)

    def test_report_schema_is_valid(self):
        Draft202012Validator.check_schema(_REPORT)


class TestEnvelope:
    def test_accepts_well_formed_document(self, access):
        doc = derive_document(_core_choices(), access)
        envelope = {
            k: doc[k]
            for k in ("core", "inventory", "grimoire", "modifier", "companion")
            if k in doc
        }
        assert list(_ENVELOPE_VALIDATOR.iter_errors(envelope)) == []

    def test_core_only_is_valid(self, access):
        doc = derive_document(_core_choices(), access)
        assert list(_ENVELOPE_VALIDATOR.iter_errors({"core": doc["core"]})) == []

    def test_rejects_missing_core(self):
        errs = list(_ENVELOPE_VALIDATOR.iter_errors({"inventory": {}}))
        assert any("core" in e.message for e in errs)

    def test_rejects_unknown_top_level_key(self, access):
        doc = derive_document(_core_choices(), access)
        env = {"core": doc["core"], "bogus": 1}
        assert list(_ENVELOPE_VALIDATOR.iter_errors(env)) != []


_MISSING_SUBCLASS = {
    "choice_key": "core.classes.0.subclass",
    "section": "core",
    "path": "classes[0].subclass",
    "resource": "subclass",
    "type": "missing",
    "count": {"required": 1, "filled": 0},
    "status": "required",
    "description": "Choose a subclass.",
}
_TOO_MANY_SKILLS = {
    "choice_key": "core.skills",
    "section": "core",
    "path": "skills",
    "resource": "skill",
    "type": "too_many",
    "count": {"max": 3, "filled": 4},
    "status": "required",
    "description": "Too many skills — maximum 3.",
}
_TOO_FEW_SPELLS = {
    "choice_key": "grimoire.spells",
    "section": "grimoire",
    "path": "spells",
    "resource": "spell",
    "type": "too_few",
    "count": {"required": 6, "filled": 2},
    "status": "required",
    "description": "4 spells still to choose.",
}


def _report(manifest, *, legal=True, complete=True, awaiting=True):
    return {
        "legal": legal,
        "complete": complete,
        "awaiting_choices": awaiting,
        "violations": [],
        "manifest": manifest,
        "summary": {"total": 0, "errors": 0, "warnings": 0},
    }


class TestReport:
    @pytest.mark.parametrize(
        "entry", [_MISSING_SUBCLASS, _TOO_MANY_SKILLS, _TOO_FEW_SPELLS]
    )
    def test_accepts_worked_examples(self, entry):
        assert list(_REPORT_VALIDATOR.iter_errors(_report([entry]))) == []

    def test_empty_manifest_is_valid(self):
        assert list(_REPORT_VALIDATOR.iter_errors(_report([], awaiting=False))) == []

    def test_rejects_bad_type(self):
        bad = dict(_MISSING_SUBCLASS, type="banana")
        assert list(_REPORT_VALIDATOR.iter_errors(_report([bad]))) != []

    def test_rejects_bad_resource(self):
        bad = dict(_MISSING_SUBCLASS, resource="not-a-kind")
        assert list(_REPORT_VALIDATOR.iter_errors(_report([bad]))) != []

    def test_rejects_bad_section(self):
        bad = dict(_MISSING_SUBCLASS, section="modifier")
        assert list(_REPORT_VALIDATOR.iter_errors(_report([bad]))) != []

    def test_rejects_entry_missing_required_field(self):
        bad = {k: v for k, v in _MISSING_SUBCLASS.items() if k != "choice_key"}
        assert list(_REPORT_VALIDATOR.iter_errors(_report([bad]))) != []

    def test_rejects_count_without_filled(self):
        bad = dict(_MISSING_SUBCLASS, count={"required": 1})
        assert list(_REPORT_VALIDATOR.iter_errors(_report([bad]))) != []
