"""Conformance: the contract adapter maps real derived sheets to documents that validate against
`contracts/character-sheet.schema.json`. Runs on the synthetic catalog (no game content)."""
import json
import pathlib

from jsonschema import Draft202012Validator

from app.contract import to_contract_sheet
from app.derivation import derive

_SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[1] / "contracts" / "character-sheet.schema.json").read_text())


def _errors(obj) -> list:
    return sorted(f"{list(e.path)}: {e.message}"
                  for e in Draft202012Validator(_SCHEMA).iter_errors(obj))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(_SCHEMA)


def _choices(**over):
    c = {"name": "Test Hero", "race": "Human", "alignment": "Balance", "background": "Scholar",
         "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10},
         "skill_choices": ["Lore", "Runes"],
         "spell_choices": {"cantrips": ["Spark", "Glimmer", "Whisper"],
                           "spells": ["Bolt", "Ward", "Mist", "Veil"]}}
    c.update(over)
    return c


def test_caster_sheet_conforms(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3, "subclass": "Evoker"}])
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["spellcasting"] is not None
    assert contract["abilities"]["int"] == {"base": 15, "racial_bonus": 1, "final": 16, "modifier": 3}  # lvl 3: no ASI yet
    assert _errors(contract) == []


def test_noncaster_sheet_conforms(catalog):
    choices = _choices(classes=[{"class": "Warrior", "level": 3}], name="Bran",
                       skill_choices=["Brawn", "Menace"], spell_choices={})
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert contract["spellcasting"] is None
    assert _errors(contract) == []


def test_multiclass_caster_conforms(catalog):
    choices = _choices(classes=[{"class": "Warrior", "level": 3}, {"class": "Mage", "level": 2}],
                       skill_choices=["Brawn", "Menace"])
    contract = to_contract_sheet(choices, derive(catalog, choices))
    assert _errors(contract) == []


def test_meta_included_when_provided(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3}])
    request = {"race": "Human", "classes": [{"class": "Mage", "level": 3}]}
    contract = to_contract_sheet(choices, derive(catalog, choices), seed=42, request=request)
    assert contract["meta"] == {"seed": 42, "request": request}
    assert _errors(contract) == []


def test_meta_omitted_when_absent(catalog):
    choices = _choices(classes=[{"class": "Mage", "level": 3}])
    assert "meta" not in to_contract_sheet(choices, derive(catalog, choices))
