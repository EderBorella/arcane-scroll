"""Full-document generation pipeline: a character's ``choices`` → the complete five-schema document.

This is the seam that wires the existing DAL derivers together (F05-T68, S13 Phase 3). ``derive_core``
(Phase 2) produces the CORE keystone — the permanent, always-active facts. The remaining schema
derivers / orchestrators layer the rest on top of it:

* **INVENTORY** (``inventory:1``) — *assembled*, not re-derived. An inventory is a self-describing
  list of concrete item records (id + name + reference facts), so it is built by resolving the
  chosen items into records, NOT walked out of grant rows the way CORE's spine is. There is no
  separate INVENTORY deriver; :func:`assemble_inventory` is the minimal assembly.
* **GRIMOIRE** (``grimoire:1``) — ``derive_grimoire(core, …)``. Emitted when the build has a CLASS
  spellcasting progression (a spellcasting class or a spellcasting subclass — including a third-caster
  subclass) OR an innate species/lineage spell grant. An innate cantrip is represented as its own
  GRIMOIRE source category (kind ``species`` / ``lineage``) so it is not dropped (F05-T81). A build
  whose ONLY spell source is a feat carries no GRIMOIRE here (a separate representation).
* **MODIFIER** (``modifier-sheet:1``) — ``derive_modifier(core, inventory, grimoire, …)``: the
  live/effective layer (effective abilities/AC/speed/defences, resource state, item/character states).
* **COMPANION** (``companion-modifier:1``) — ``derive_companions(core, …)``. Emitted only when the
  build actually has companions.

The assembled document is ``{core, inventory, grimoire?, modifier, companion?}`` — GRIMOIRE and
COMPANION are omitted when the build has neither spellcasting nor companions. Every schema of the
document passes its validator for a legal set of choices.

Content-neutral: names resolve from the loaded ruleset via ``access/``; no game literals live here.
"""
from typing import Any

from access.generator import equipment as equip_q
from app.derivation.companion_orchestrator import derive_companions
from app.derivation.core import derive_core
from app.derivation.grimoire import derive_grimoire, hash_core
from app.derivation.modifier_orchestrator import derive_modifier

Choices = dict[str, Any]

# The item-record fields the inventory:1 contract recognises beyond the required id + name. A chosen
# item spec may carry any of these; they pass through verbatim so the assembly stays edition-agnostic
# (the values are catalog facts, resolved by the generator upstream, never rule math here).
_ITEM_PASSTHROUGH = (
    "category", "quantity", "weight", "description", "magic", "rarity", "properties",
    "damage_dice", "versatile_damage", "damage_type", "mastery", "range",
    "armor_category", "base_ac", "dex_cap", "stealth_disadvantage", "strength_req",
    "ac_bonus", "spell_id", "template_item", "base_item", "charges",
)


def _item_record(spec: Any, seq: int, access) -> dict | None:
    """One inventory item record from a chosen item spec, enriched with its catalog facts.

    A spec is either a bare item name (string) or a dict carrying at least ``name`` plus any of the
    optional inventory:1 item fields. A sheet-local ``id`` is assigned when the spec omits one, so
    every item carries the unique id the contract (and MODIFIER's item_states) reference it by.

    Any inventory:1 field the spec already carries is kept verbatim; the catalog fills in the rest
    (category, weight, weapon / armour facts) so a generated record reaches corpus fidelity without
    the caller having to spell every fact out (F05-T80)."""
    if isinstance(spec, str):
        spec = {"name": spec}
    if not isinstance(spec, dict):
        return None
    name = spec.get("name")
    if not name:
        return None
    record: dict = {"id": spec.get("id") or f"item-{seq}", "name": name}
    for key in _ITEM_PASSTHROUGH:
        if key in spec:
            record[key] = spec[key]
    for key, value in _catalog_enrichment(access, name).items():
        record.setdefault(key, value)
    return record


def _damage_dice(count, faces) -> str | None:
    """A weapon's base damage dice as a ``NdM`` string, or None when the DB carries no dice (a
    ranged weapon that fires ammunition, say)."""
    if count and faces:
        return f"{count}d{faces}"
    return None


def _catalog_enrichment(access, name: str) -> dict:
    """The inventory:1 catalog facts for an item resolved by name — category, weight, and the
    weapon / armour facts that apply. Empty when the name resolves to no catalog item. Reads are
    pure (via ``access/generator/equipment``); only non-null facts are attached, mirroring how the
    other derivers omit absent optionals rather than emitting nulls."""
    cid = access.resolve("catalog_item", name)
    if cid is None:
        return {}
    facts: dict = {}

    base = equip_q.catalog_item_facts(access, cid)
    if base:
        if base["kind"]:
            facts["category"] = base["kind"]
        if base["weight"] is not None:
            facts["weight"] = base["weight"]

    weapon = equip_q.weapon_facts(access, cid)
    if weapon:
        dice = _damage_dice(weapon["dmg_dice_count"], weapon["dmg_die_faces"])
        if dice:
            facts["damage_dice"] = dice
        if weapon["damage_type_id"]:
            facts["damage_type"] = weapon["damage_type_id"]
        if weapon["mastery_id"]:
            facts["mastery"] = weapon["mastery_id"]
        facts["properties"] = weapon["properties"]

    armor = equip_q.armor_facts(access, cid)
    if armor:
        if armor["category_id"]:
            facts["armor_category"] = armor["category_id"]
        if armor["base_ac"] is not None:
            facts["base_ac"] = armor["base_ac"]
        if armor["dex_cap"] is not None:
            facts["dex_cap"] = armor["dex_cap"]
        if armor["ac_bonus"] is not None:
            facts["ac_bonus"] = armor["ac_bonus"]
        if armor["strength_req"] is not None:
            facts["strength_req"] = armor["strength_req"]
        facts["stealth_disadvantage"] = bool(armor["stealth_disadvantage"])

    return facts


def assemble_inventory(choices: Choices, core: dict, access) -> dict:
    """Assemble an ``inventory:1`` document from the equipment choices.

    INVENTORY is an assembly, not a deriver: an item is a self-describing record, so the generator's
    chosen items are resolved into ``equipped`` (keyed by body slot) and ``backpack`` records rather
    than re-derived from grant rows. The equipment choices live under ``choices["equipment"]``::

        {"equipped": {slot_id: item_spec, ...}, "backpack": [item_spec, ...]}

    An empty (or absent) equipment choice yields a legal empty inventory — the unarmoured, gearless
    build the MODIFIER layer then reads (AC 10 + Dex, no worn armour). Item ids are assigned across
    both containers so no two items collide. ``access`` resolves each item's catalog facts so the
    emitted records carry the reference facts (category, weight, weapon / armour facts), not just the
    id + name the choices supply (F05-T80).
    """
    equipment = choices.get("equipment") or {}
    if not isinstance(equipment, dict):
        equipment = {}

    seq = 0
    equipped: dict[str, dict] = {}
    for slot, spec in (equipment.get("equipped") or {}).items():
        record = _item_record(spec, seq, access)
        if record is not None:
            equipped[slot] = record
            seq += 1

    backpack: list[dict] = []
    for spec in equipment.get("backpack") or []:
        record = _item_record(spec, seq, access)
        if record is not None:
            backpack.append(record)
            seq += 1

    return {
        "schema_version": 1,
        "character_id": core.get("character_id", ""),
        "character_name": core.get("character_name", ""),
        "derived_from_core": hash_core(core),
        "equipped": equipped,
        "backpack": backpack,
    }


# The source ``kind`` values (from grimoire.derive_sources) that warrant a GRIMOIRE sheet: a CLASS
# spellcasting progression (a spellcasting class or subclass) OR an innate species/lineage spell
# grant. Innate cantrips are represented as their own GRIMOIRE source category so they are not
# dropped (F05-T81). Feat-granted spells remain excluded — their representation is a separate card.
_GRIMOIRE_SOURCE_KINDS = ("class", "subclass", "species", "lineage")


def _has_grimoire_source(grimoire: dict) -> bool:
    """True when the GRIMOIRE carries a source that warrants a sheet — a class / subclass spellcasting
    progression or an innate species / lineage grant. A build whose only spell source is a feat is
    NOT represented by a GRIMOIRE sheet here."""
    sources = grimoire.get("sources") or {}
    return any(isinstance(s, dict) and s.get("kind") in _GRIMOIRE_SOURCE_KINDS
               for s in sources.values())


def derive_document(choices: Choices, access) -> dict:
    """Materialise the full five-schema character document from a generated character's ``choices``.

    ``access`` is any data-access handle exposing ``.db`` / ``.resolve`` / ``.resolver`` (a
    ``GeneratorAccess`` or ``ValidatorAccess``). Returns ``{core, inventory, grimoire?, modifier,
    companion?}`` — GRIMOIRE is present only for a spellcasting build and COMPANION only when the
    build has companions. Each schema passes its validator for a legal set of choices.
    """
    core = derive_core(choices, access)
    inventory = assemble_inventory(choices, core, access)

    grimoire_full = derive_grimoire(core, None, access, chosen_spells=choices.get("spells"))
    grimoire = grimoire_full if _has_grimoire_source(grimoire_full) else None

    modifier, _mod_meta = derive_modifier(core, inventory, grimoire, None, "full", access,
                                          starting_treasure=choices.get("treasure"))
    companion, _comp_meta = derive_companions(core, None, "full", access, grimoire)

    document: dict = {"core": core, "inventory": inventory, "modifier": modifier}
    if grimoire is not None:
        document["grimoire"] = grimoire
    if companion.get("companion_modifiers"):
        document["companion"] = companion
    return document
