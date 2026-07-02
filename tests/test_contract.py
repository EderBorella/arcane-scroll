"""The contract (`contracts/character-sheet.schema.json` v2) and its example are self-consistent.

NOTE: the generator (`app/`) has NOT been migrated to v2 and does NOT conform — that non-conformance
is the *intended, measured* gap of an independent validator, fixed later and NEVER by editing the
generator (see CLAUDE.md). The generator→contract conformance tests below are therefore `xfail` until
that separate generator task runs; do not "fix" them by changing `app/`."""
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.contract import to_contract_sheet
from app.derivation import derive

_CONTRACTS = pathlib.Path(__file__).parents[1] / "contracts"
_SCHEMA = json.loads((_CONTRACTS / "character-sheet.schema.json").read_text())
_ITEM = json.loads((_CONTRACTS / "item.schema.json").read_text())
# Registry so the sheet's external $ref to the item contract resolves.
_REGISTRY = Registry().with_resources([
    (_SCHEMA["$id"], Resource.from_contents(_SCHEMA)),
    (_ITEM["$id"], Resource.from_contents(_ITEM)),
])
_VALIDATOR = Draft202012Validator(_SCHEMA, registry=_REGISTRY)

_GEN_GAP = "generator not migrated to contract v2; its non-conformance is the intended, measured gap"


def _errors(obj) -> list:
    return sorted(f"{list(e.path)}: {e.message}" for e in _VALIDATOR.iter_errors(obj))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(_SCHEMA)
    Draft202012Validator.check_schema(_ITEM)


def test_example_fixture_conforms():
    example = json.loads((_CONTRACTS / "examples" / "minimal.sheet.json").read_text())
    assert _errors(example) == []


def _choices(**over):
    c = {"name": "Test Hero", "race": "Human", "alignment": "Balance", "background": "Scholar",
         "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10},
         "skill_choices": ["Lore", "Runes"],
         "spell_choices": {"cantrips": ["Spark", "Glimmer", "Whisper"],
                           "spells": ["Bolt", "Ward", "Mist", "Veil"]}}
    c.update(over)
    return c


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_caster_sheet_conforms(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3, "subclass": "Evoker"}])
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["spellcasting"] is not None
    assert contract["abilities"]["int"] == {"base": 15, "racial_bonus": 1, "final": 16, "modifier": 3}  # lvl 3: no ASI yet
    assert _errors(contract) == []


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_noncaster_sheet_conforms(catalog):
    choices = _choices(classes=[{"class": "Warrior", "level": 3}], name="Bran",
                       skill_choices=["Brawn", "Menace"], spell_choices={})
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["spellcasting"] is None
    assert _errors(contract) == []


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_multiclass_caster_conforms(catalog):
    choices = _choices(classes=[{"class": "Warrior", "level": 3}, {"class": "Mage", "level": 2}],
                       skill_choices=["Brawn", "Menace"])
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert _errors(contract) == []


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_meta_included_when_provided(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3}])
    request = {"race": "Human", "classes": [{"class": "Mage", "level": 3}]}
    contract = to_contract_sheet(choices, derive(catalog, choices), seed=42, request=request)
    assert contract["meta"] == {"seed": 42, "request": request}
    assert _errors(contract) == []


def test_meta_omitted_when_absent(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3}])
    assert "meta" not in to_contract_sheet(choices, derive(catalog, choices))


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_weapon_sheet_conforms(catalog):
    choices = _choices(classes=[{"class": "Warrior", "level": 3}], skill_choices=["Brawn", "Menace"],
                       spell_choices={}, equipment_0="Club")
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert any(a["name"] == "Club" for a in contract["attacks"])
    assert _errors(contract) == []


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_land_type_surfaced_on_class_entry(catalog):
    choices = _choices(classes=[{"class": "Oracle", "level": 3, "subclass": "Landwarden"}], land_type="LandA")
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["identity"]["classes"][0]["subclass_detail"] == "LandA"
    assert _errors(contract) == []


def test_no_subclass_detail_when_not_land(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3, "subclass": "Evoker"}])
    ce = to_contract_sheet(choices, derive(catalog, choices))["identity"]["classes"][0]
    assert "subclass_detail" not in ce


@pytest.mark.xfail(reason=_GEN_GAP, strict=False)
def test_third_caster_subclass_sheet_conforms(catalog):
    # pure Eldritch Knight: has slots + spells; spellcasting.classes must be non-empty (T64)
    choices = _choices(classes=[{"class": "Fighter", "level": 3, "subclass": "Eldritch Knight"}],
                       skill_choices=["Brawn", "Menace"],
                       spell_choices={"cantrips": ["Spark"], "spells": ["Bolt"]})
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["spellcasting"]["classes"]        # was {} before the fix → schema failure
    assert _errors(contract) == []
