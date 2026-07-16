"""Full-document generation pipeline: a character's ``choices`` → the complete five-schema document.

This is the seam that wires the existing DAL derivers together (F05-T68, S13 Phase 3). ``derive_core``
(Phase 2) produces the CORE keystone — the permanent, always-active facts. The remaining schema
derivers / orchestrators layer the rest on top of it:

* **INVENTORY** (``inventory:1``) — *assembled*, not re-derived. An inventory is a self-describing
  list of concrete item records (id + name + reference facts), so it is built by resolving the
  chosen items into records, NOT walked out of grant rows the way CORE's spine is. There is no
  separate INVENTORY deriver; :func:`assemble_inventory` is the minimal assembly.
* **GRIMOIRE** (``grimoire:1``) — ``derive_grimoire(core, …)``. Emitted only when the build has a
  CLASS spellcasting progression (a spellcasting class or a spellcasting subclass — including a
  third-caster subclass). A build whose ONLY spell source is innate (a species/lineage cantrip) or a
  feat is NOT a class caster and carries no GRIMOIRE, matching the corpus, which reserves grimoire
  sheets for class spellcasters.
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


def _item_record(spec: Any, seq: int) -> dict | None:
    """One inventory item record from a chosen item spec.

    A spec is either a bare item name (string) or a dict carrying at least ``name`` plus any of the
    optional inventory:1 item fields. A sheet-local ``id`` is assigned when the spec omits one, so
    every item carries the unique id the contract (and MODIFIER's item_states) reference it by."""
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
    return record


def assemble_inventory(choices: Choices, core: dict, access) -> dict:
    """Assemble an ``inventory:1`` document from the equipment choices.

    INVENTORY is an assembly, not a deriver: an item is a self-describing record, so the generator's
    chosen items are resolved into ``equipped`` (keyed by body slot) and ``backpack`` records rather
    than re-derived from grant rows. The equipment choices live under ``choices["equipment"]``::

        {"equipped": {slot_id: item_spec, ...}, "backpack": [item_spec, ...]}

    An empty (or absent) equipment choice yields a legal empty inventory — the unarmoured, gearless
    build the MODIFIER layer then reads (AC 10 + Dex, no worn armour). Item ids are assigned across
    both containers so no two items collide. ``access`` is unused today (records pass through from the
    choices) but is part of the signature so a later enrichment pass can resolve catalog facts here.
    """
    equipment = choices.get("equipment") or {}
    if not isinstance(equipment, dict):
        equipment = {}

    seq = 0
    equipped: dict[str, dict] = {}
    for slot, spec in (equipment.get("equipped") or {}).items():
        record = _item_record(spec, seq)
        if record is not None:
            equipped[slot] = record
            seq += 1

    backpack: list[dict] = []
    for spec in equipment.get("backpack") or []:
        record = _item_record(spec, seq)
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


# The source ``kind`` values (from grimoire.derive_sources) that represent a CLASS spellcasting
# progression. Innate sources (species/lineage) and feat-granted spells are deliberately excluded:
# they do not, on their own, warrant a GRIMOIRE sheet under the corpus convention.
_CLASS_CASTER_KINDS = ("class", "subclass")


def _has_class_spellcasting(grimoire: dict) -> bool:
    """True when the GRIMOIRE carries a CLASS spellcasting progression — a spellcasting class or a
    spellcasting subclass source. A build whose only spell source is innate (species/lineage) or a
    feat is NOT a class caster, so it produces no GRIMOIRE sheet (matching the corpus, which reserves
    grimoire files for class spellcasters)."""
    sources = grimoire.get("sources") or {}
    return any(isinstance(s, dict) and s.get("kind") in _CLASS_CASTER_KINDS
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
    grimoire = grimoire_full if _has_class_spellcasting(grimoire_full) else None

    modifier, _mod_meta = derive_modifier(core, inventory, grimoire, None, "full", access)
    companion, _comp_meta = derive_companions(core, None, "full", access, grimoire)

    document: dict = {"core": core, "inventory": inventory, "modifier": modifier}
    if grimoire is not None:
        document["grimoire"] = grimoire
    if companion.get("companion_modifiers"):
        document["companion"] = companion
    return document
