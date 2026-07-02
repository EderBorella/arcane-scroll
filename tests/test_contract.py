"""The contract (`contracts/character-sheet.schema.json`) and its example are self-consistent, plus
a regression suite that pins the contract's promises so a future version can't silently loosen them.

NOTE: the generator (`app/`) has NOT been migrated to the current contract and does NOT conform — that
non-conformance is the *intended, measured* gap of an independent validator, fixed later and NEVER by
editing the generator (see CLAUDE.md). The generator→contract conformance tests below are therefore
`xfail` until that separate generator task runs; do not "fix" them by changing `app/`."""
import copy
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

_GEN_GAP = "generator not migrated to the current contract; its non-conformance is the intended, measured gap"


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


# --- Regression guards ------------------------------------------------------------------------
# Each case starts from the known-good example, mutates ONE thing, and asserts the contract now
# rejects it. This pins the promises the contract makes; a future version that silently drops a
# constraint makes the matching case pass validation, which fails the test and forces a conscious
# decision. If a later version *intentionally* changes a rule, update the case in the same commit.

_EXAMPLE = json.loads((_CONTRACTS / "examples" / "minimal.sheet.json").read_text())
_DELETE = object()


def _mutated(path, value):
    """A deep copy of the example with `path` set to `value` (or deleted when value is _DELETE)."""
    sheet = copy.deepcopy(_EXAMPLE)
    *parents, last = path
    node = sheet
    for key in parents:
        node = node[key]
    if value is _DELETE:
        del node[last]
    else:
        node[last] = value
    return sheet


# name -> (path into the sheet, new value | _DELETE) — the mutation the contract MUST reject.
_REJECT_CASES = {
    "base_above_20":              (["abilities", "a1", "base"], 21),          # base is pre-increase, capped at 20
    "final_above_30":             (["abilities", "a1", "final"], 31),         # final caps at 30 even with boons
    "missing_background":         (["identity", "background"], _DELETE),      # background is mandatory
    "empty_feats":                (["feats"], []),                            # at least the origin feat
    "spellcasting_without_sources":(["spellcasting", "sources"], _DELETE),    # a casting block needs >=1 source
    "empty_sources":              (["spellcasting", "sources"], {}),          # sources must record >=1 source
    "casting_source_without_kind":(["spellcasting", "sources", "class-a", "kind"], _DELETE),  # a source must declare its kind
    "unknown_top_level_field":    (["bogus"], 1),                             # additionalProperties: false
    "legacy_inventory_field":     (["inventory"], []),                        # replaced by equipped + backpack
    "exhaustion_out_of_range":    (["exhaustion"], 7),                        # 0..6
    "too_many_death_saves":       (["combat", "death_saves", "successes"], 4),# 0..3
    "wrong_schema_version":       (["schema_version"], 999),                  # const-pinned
    "proficiency_bonus_below_2":  (["proficiency_bonus"], 1),                 # 2..6
    "unknown_item_field":         (["equipped", "slot-a", "bogus"], 1),       # item additionalProperties: false
    "slot_pool_without_remaining":(["spellcasting", "spell_slots", "1", "remaining"], _DELETE),  # live-state pool needs remaining
    "hit_dice_without_remaining": (["combat", "hit_dice", "d8", "remaining"], _DELETE),          # live-state pool needs remaining
    "companion_without_name":     (["companions"], [{"kind": "kind-a"}]),     # companion requires name
    "ac_bonus_without_source":    (["combat", "armor_class_detail", "bonuses"], [{"value": 1}]),  # AC bonus must name its source
    "empty_spell_slots":          (["spellcasting", "spell_slots"], {}),      # a present slot table must record >=1 level
    "ammunition_without_type":    (["equipped", "slot-e", "ammunition"], {"count": 5}),           # ammunition requires its type
    "charges_without_max":        (["equipped", "slot-c", "charges"], {"remaining": 1}),          # a charge pool requires max
}


@pytest.mark.parametrize("name", sorted(_REJECT_CASES))
def test_contract_rejects_regression(name):
    assert _errors(_mutated(*_REJECT_CASES[name])) != [], f"{name}: should be rejected but conformed"


def test_pact_only_spellcasting_conforms():
    """Guards the anyOf(spell_slots | pact_slots): a pact caster has pact_slots and no leveled slots."""
    sheet = copy.deepcopy(_EXAMPLE)
    del sheet["spellcasting"]["spell_slots"]
    sheet["spellcasting"]["pact_slots"] = {"1": {"max": 2, "remaining": 2}}
    assert _errors(sheet) == []


def test_noncaster_spellcasting_null_conforms():
    """Guards the oneOf null branch: a wholly non-casting character has spellcasting = null."""
    assert _errors(_mutated(["spellcasting"], None)) == []


def test_both_slot_kinds_conform():
    """A multiclass traditional+pact caster carries both spell_slots and pact_slots at once."""
    sheet = copy.deepcopy(_EXAMPLE)
    sheet["spellcasting"]["pact_slots"] = {"1": {"max": 2, "remaining": 2}}
    assert _errors(sheet) == []


def test_slotless_caster_conforms():
    """A caster whose only spells come from a slotless source (species cantrip, origin feat) has a
    sources block and spells but NO slot tables at all — e.g. a martial with Magic Initiate."""
    sheet = copy.deepcopy(_EXAMPLE)
    del sheet["spellcasting"]["spell_slots"]
    assert "pact_slots" not in sheet["spellcasting"]
    assert _errors(sheet) == []


def test_schema_version_matches_id():
    """A version bump must move the $id tail and the schema_version const together."""
    assert _SCHEMA["$id"].rsplit(":", 1)[-1] == str(_SCHEMA["properties"]["schema_version"]["const"])


def test_item_ref_matches_item_id():
    """The sheet's single item alias must point at the item schema's own $id."""
    assert _SCHEMA["$defs"]["item"]["$ref"] == _ITEM["$id"]
