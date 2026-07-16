# Arcane Scroll — Contract Schemas

The single-source-of-truth contracts for character sheet data across the Arcane projects. Each schema
is independently versioned via its `$id` URN and uses [JSON Schema Draft 2020-12](https://json-schema.org/).

## The 5-schema split (v1)

| Schema | URN | Purpose | When it changes |
|--------|-----|---------|-----------------|
| **CORE** | `urn:arcane:contract:core-sheet:1` | Permanent, always-active facts. No live-play counters, no spells, no items. | Level-up, feat choice, species/background choice. |
| **INVENTORY** | `urn:arcane:contract:inventory:1` | Item records — equipped and carried. Catalog-ref facts + quantity. | Acquire, consume, lose, or trade items. |
| **GRIMOIRE** | `urn:arcane:contract:grimoire:1` | Spellcasting maximums. Derived from CORE + DB. No remaining counters. | Level-up, learn/scribe spells, subclass unlock. |
| **MODIFIER** | `urn:arcane:contract:modifier-sheet:1` | Live-play, derived, and conditional state. Counters, effective values, character states. | Every round, every rest, every spell cast, every hit taken. |
| **COMPANION_MODIFIER** | `urn:arcane:contract:companion-modifier:1` | Companion gameplay stats. Links to CORE companion identity. | Every round for the companion, every rest. |

All 5 schemas share `character_id` (UUID) and `character_name`.

### Standalone monster sheet

| Schema | URN | Purpose | When it changes |
|--------|-----|---------|-----------------|
| **MONSTER_SHEET** | `urn:arcane:contract:monster-sheet:1` | A sheet of one or more OWNER-LESS materialised monsters (concrete catalogued creatures). Each entry references the SHARED owner-agnostic stat-block base (`$ref` to `companion-modifier:1#/$defs/statBlockBase`) and carries its own `creature_id`; being owner-less it has no `companion_index` (a monster's position is its index in `monsters[]`). | New/changed catalogued creature stats. |

A materialised monster is a concrete creature with no owner — essentially a concrete
companion detached from a character. Templated (owner-scaled) creatures cannot appear
on a monster sheet: their stats only exist relative to an owner's cast level, so they
are rejected at materialisation and validation, never emitted with un-scaled zeros.
This sheet has no `character_id` / `character_name` (there is no character).

## Derivation flow

```
CORE ──▶ Core Validator
  │
  ├──▶ GRIMOIRE = derive(CORE, DB) ──▶ Grimoire Validator
  │
  ├──▶ MODIFIER = derive(CORE, INVENTORY, GRIMOIRE, DB) ──▶ Modifier Validator
  │
  └──▶ COMPANION_MODIFIER (after T27 monsters catalog)
```

INVENTORY is read by the MODIFIER deriver but is player-managed — the deriver never writes to it.

## MODIFIER deriver modes

| Mode | Input | Behaviour |
|------|-------|-----------|
| **(a) Full derivation** | CORE + INVENTORY + GRIMOIRE | Fill all MODIFIER fields from scratch |
| **(b) Gap-fill** | Above + partially filled MODIFIER | Fill missing derivable fields, protect non-overwritable fields, then validate |
| **(c) Validate only** | Above + fully filled MODIFIER | Skip derivation, validate all fields |

The **validator ALWAYS runs** — modes (a) and (b) validate after derivation; mode (c) validates the
pre-filled sheet. Mode (b) overwrites derivable pre-filled values but never touches non-overwritable
fields.

## Non-overwritable MODIFIER fields (18 entries)

The deriver never overwrites these when pre-filled in mode (b):

```
character_states[], hit_points.current, hit_points.temp, death_saves.*,
hit_dice.*.remaining, spell_slots.*.remaining, pact_slots.*.remaining,
resource_state.*.remaining, features[].uses.remaining, feats[].uses.remaining,
item_states[].attuned, item_states[].consumed, item_states[].charges.remaining,
item_states[].cumulative_seconds_used, prepared_spells, treasure.*, xp
```

## Design rules

- **Content-neutral.** All 5 schemas are structural only. Game vocabulary (ability/skill/class/spell/
  species/condition names) is catalog-driven and never hard-coded.
- **additionalProperties: false** at root of every schema — no field may appear without being defined.
- **Legacy contract.** `item.schema.json` (v3) remains for backward compatibility during migration
  (Phase D). It will be removed after migration is complete. The monolithic `character-sheet.schema.json`
  (v10) has been retired — the five sub-schemas replaced it and nothing consumed it.

## Legacy field migration

The old v10 `character-sheet.schema.json` single-contract fields split as follows:

| v10 field | New home(s) |
|-----------|-------------|
| `identity` (minus `xp`) | CORE |
| `identity.xp` | MODIFIER (non-overwritable) |
| `abilities` (base/final) | CORE |
| `abilities` (modifier/reduction) | MODIFIER |
| `saving_throws` (proficient) | CORE |
| `saving_throws` (modifier) | MODIFIER |
| `skills` (ability/proficient/expertise/source) | CORE |
| `skills` (modifier) | MODIFIER |
| `passive_scores` | MODIFIER |
| `proficiency_bonus` | CORE |
| `senses` | CORE (`permanent_senses`) + MODIFIER (`effective_senses`) |
| `defenses` | CORE (`permanent_defenses`) + MODIFIER (`effective_defenses`) |
| `combat.speed` | CORE (`permanent_speed`) + MODIFIER (`speed` + `speed_detail`) |
| `combat.armor_class` + `armor_class_detail` | MODIFIER |
| `combat.initiative` | MODIFIER |
| `combat.hit_points` | CORE (`max`) + MODIFIER (`current/temp/max_reduction/max_boost`) |
| `combat.hit_dice` | CORE (`max`) + MODIFIER (`remaining`) |
| `combat.death_saves` | MODIFIER |
| `heroic_inspiration`, `conditions`, `exhaustion`, `active_concentration`, `active_effects` | MODIFIER (`character_states[]` — unified) |
| `equipped`, `backpack` | INVENTORY (catalog-refs) + MODIFIER (`item_states[]` — live-play) |
| `treasure` | MODIFIER |
| `attunement` | MODIFIER (`item_states[].attuned`) |
| `class_resources` | CORE (`resource_budgets`) + MODIFIER (`resource_state`) |
| `features` | CORE (definition) + MODIFIER (always-appear with `uses`) |
| `feats` | CORE (definition) + MODIFIER (always-appear with `uses`) |
| `spellcasting` | GRIMOIRE (max values + spell metadata) + MODIFIER (remaining counters + modifier/DC/attack_bonus) |
| `companions` | CORE (identity) + COMPANION_MODIFIER (gameplay stats) |
| `permanent_effects` | CORE |
| `flavour` | CORE |

## Validating

Any Draft 2020-12 validator. Example (Python):

```python
import json
from jsonschema import Draft202012Validator

for schema_file in [
    "core-sheet.schema.json",
    "inventory.schema.json",
    "grimoire.schema.json",
    "modifier-sheet.schema.json",
    "companion-modifier.schema.json",
]:
    schema = json.load(open(f"contracts/{schema_file}"))
    Draft202012Validator.check_schema(schema)  # verify the schema is valid
```

## Generating types

- **Python (Pydantic v2):** `datamodel-code-generator --input <schema>.json --input-file-type jsonschema --output models.py`
- **TypeScript:** `json-schema-to-typescript <schema>.json > types.ts`
