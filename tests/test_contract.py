"""The legacy monolithic contract (`contracts/character-sheet.schema.json`) and its example are
self-consistent, plus a regression suite that pins the contract's promises so a future version can't
silently loosen them.

The generator no longer targets this monolithic contract: the generation endpoint emits the
five-schema document (`{core, inventory, grimoire?, modifier, companion?}`), and its conformance to
each live sub-schema is exercised end-to-end in `tests/controllers/test_generation.py` (endpoint) and
`tests/generation/test_choices_grammar.py` (pipeline). This file continues to pin the shape of the
retained monolithic schema fixture."""
import copy
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_CONTRACTS = pathlib.Path(__file__).parents[1] / "contracts"
_SCHEMA = json.loads((_CONTRACTS / "character-sheet.schema.json").read_text())
_ITEM = json.loads((_CONTRACTS / "item.schema.json").read_text())
# Registry so the sheet's external $ref to the item contract resolves.
_REGISTRY = Registry().with_resources([
    (_SCHEMA["$id"], Resource.from_contents(_SCHEMA)),
    (_ITEM["$id"], Resource.from_contents(_ITEM)),
])
_VALIDATOR = Draft202012Validator(_SCHEMA, registry=_REGISTRY)


def _errors(obj) -> list:
    return sorted(f"{list(e.path)}: {e.message}" for e in _VALIDATOR.iter_errors(obj))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(_SCHEMA)
    Draft202012Validator.check_schema(_ITEM)


def test_example_fixture_conforms():
    example = json.loads((_CONTRACTS / "examples" / "minimal.sheet.json").read_text())
    assert _errors(example) == []


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
    "speed_modifier_without_source": (["combat", "speed_detail", "modifiers"], [{"mode": "mode-a", "value": 5}]),  # modifier must name its source
    "speed_modifier_neither_value_nor_relative": (["combat", "speed_detail", "modifiers"], [{"mode": "mode-a", "source": "feat-a"}]),  # need exactly one of value|relative
    "speed_relative_without_of": (["combat", "speed_detail", "modifiers"], [{"mode": "mode-c", "source": "feature-b", "relative": {"factor": 1}}]),  # relative requires `of`
    "empty_spell_slots":          (["spellcasting", "spell_slots"], {}),      # a present slot table must record >=1 level
    "ammunition_without_type":    (["equipped", "slot-e", "ammunition"], {"count": 5}),           # ammunition requires its type
    "charges_without_max":        (["equipped", "slot-c", "charges"], {"remaining": 1}),          # a charge pool requires max
    "spell_uses_without_max":     (["spellcasting", "spells", 4, "uses"], {"remaining": 1}),      # a slotless spell's use pool requires max
}


@pytest.mark.parametrize("name", sorted(_REJECT_CASES))
def test_contract_rejects_regression(name):
    assert _errors(_mutated(*_REJECT_CASES[name])) != [], f"{name}: should be rejected but conformed"


def test_pact_only_spellcasting_conforms():
    """A pact caster carries pact_slots and no leveled spell_slots — slots are optional, but a
    present pact_slots table must be non-empty (slotTable minProperties)."""
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
