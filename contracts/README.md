# Character-sheet contract

`character-sheet.schema.json` is the **single source of truth** for the shape of a character sheet
across the Arcane projects — a versioned [JSON Schema (Draft 2020-12)](https://json-schema.org/)
describing a complete, render-ready sheet.

It is **contract-first**: authored and agreed here, then every consumer is made to conform to it. It
is hosted in this repo for now, but is deliberately standalone and content-neutral so the validator
micro-service, the unique-phrase decoder and Arcane Desk can all consume it (copy / submodule /
generate types from it).

## Consumers (dependency direction)

```
arcane-scroll (generator)  ── produces  ─┐
validator micro-service    ── checks    ─┼─▶  character-sheet.schema.json
unique-phrase decoder      ── pre-fills ─┤
arcane-desk (frontend)     ── renders   ─┘
```

## Design

- **Contract-first.** Change the schema here first, bump `schema_version`, then update consumers.
  Reshape the *generator* to match the contract, not the contract to match today's output
  (tracked as board `F01-T60`).
- **Content-neutral.** Structural only. Game vocabulary (ability / skill / class / spell / background
  / race names) is **catalog-driven** and never hard-coded: those maps use `additionalProperties`
  keyed by catalog identifiers, so nothing here trips the repo content scan.
- **Legality vs. flavour.** `flavour` (personality / physical / backstory) is optional, populated by
  the backstory step, and explicitly **ignored by the validator**. Everything else is mechanical.
- **Non-casters.** `spellcasting` is `null` for a wholly non-casting character.

## Field map (official character sheet → contract block)

| Block | Official sheet section |
|---|---|
| `identity` | header (name, class & level, background, race, alignment, XP) |
| `abilities`, `proficiency_bonus` | ability scores + proficiency bonus |
| `saving_throws`, `skills`, `passive_scores` | saves, skills, passive scores (incl. perception) |
| `combat`, `defenses` | AC, initiative, speed, HP, hit dice, death saves; resistances/immunities |
| `attacks` | attacks & spellcasting (weapon rows) |
| `proficiencies`, `languages` | other proficiencies & languages |
| `equipped`, `backpack`, `treasure` | worn/wielded items, carried items, coin |
| `features` | features & traits |
| `spellcasting` | the spellcasting page |
| `flavour` | page-2 details + personality + backstory (out of scope for legality) |

## Versioning

`schema_version` is a single integer, currently **4**. Bump it on any breaking change; keep old
versions alongside if a consumer needs to migrate gradually.

## Generating types

- **Python (Pydantic v2):** `datamodel-code-generator --input character-sheet.schema.json --input-file-type jsonschema --output models.py`
- **TypeScript:** `json-schema-to-typescript character-sheet.schema.json > CharacterSheet.ts`

## Validating

Any Draft 2020-12 validator. Example (Python):

```python
import json
from jsonschema import Draft202012Validator
schema = json.load(open("contracts/character-sheet.schema.json"))
Draft202012Validator.check_schema(schema)                 # the schema itself is valid
Draft202012Validator(schema).validate(my_sheet)           # a sheet conforms
```

`examples/minimal.sheet.json` is a content-neutral placeholder sheet that validates against the
schema (used as a smoke test).
