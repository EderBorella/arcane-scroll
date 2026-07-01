"""Adapter — translate the generator's output into the shared CharacterSheet contract shape
(`contracts/character-sheet.schema.json`).

This is a deliberately **thin, pure mapping layer**: it reshapes the two things the generator already
produces — the model's `choices` and the derived `sheet` (from `app.derivation.derive`) — into one
contract-conformant document. It recomputes nothing.

Because it only maps what's available, it also documents (see GAPS) what the current generator output
cannot yet supply for the contract — the concrete follow-ups for making the generator natively emit
this shape.
"""

SCHEMA_VERSION = 1

# Contract fields the current generator output cannot fill (all optional in the schema):
#   * attacks — structured weapon rows; a mini-feature (see board F01-T61).
#   * flavour — produced by the separate /backstory endpoint, not the sheet path (by design).
GAPS = ("attacks", "flavour")


def _class_entry(c: dict) -> dict:
    return {"class": c["class"], "level": c["level"], "subclass": c.get("subclass")}


def _spellcasting(sheet: dict):
    casting = sheet.get("spellcasting") or {}
    slots = sheet.get("spell_slots") or {}
    pact = sheet.get("pact_slots") or {}
    spells = sheet.get("spells") or []
    if not (casting or slots or pact or spells):
        return None                       # a wholly non-casting character
    block = {
        "classes": casting,                                    # {class name: {ability, save_dc, attack_bonus}}
        "spell_slots": {str(k): v for k, v in slots.items()},  # keys must be strings for JSON/schema
        "spells": spells,                                      # [{name, level, prepared}]
    }
    if pact:
        block["pact_slots"] = {str(k): v for k, v in pact.items()}
    return block


def to_contract_sheet(choices: dict, sheet: dict, *, seed=None, request: dict | None = None) -> dict:
    """Map (choices, derived sheet) → a `character-sheet.schema.json` v1 document. Optional `seed`
    and `request` populate the provenance `meta` block — supplied by the endpoint that has them."""
    out = {
        "schema_version": SCHEMA_VERSION,
        "identity": {
            "name": choices.get("name") or "",
            "race": choices.get("race") or "",
            "classes": [_class_entry(c) for c in choices.get("classes", [])],
            "total_level": sheet.get("level"),
            "background": choices.get("background"),
            "alignment": choices.get("alignment"),
            "xp": sheet.get("xp", 0),
        },
        "abilities": sheet.get("abilities", {}),
        "proficiency_bonus": sheet.get("proficiency_bonus"),
        "saving_throws": sheet.get("saving_throws", {}),
        "skills": sheet.get("skills", {}),
        "passive_perception": sheet.get("passive_perception"),
        "combat": {
            "armor_class": sheet.get("armor_class"),
            "initiative": sheet.get("initiative"),
            "speed": sheet.get("speed"),
            "hit_points": {"max": sheet.get("max_hp"), "current": sheet.get("max_hp"), "temp": 0},
            "hit_dice": sheet.get("hit_dice", {}),
            "death_saves": sheet.get("death_saves", {"successes": 0, "failures": 0}),
        },
        "proficiencies": sheet.get("proficiencies", {"armor": [], "weapons": [], "tools": []}),
        "languages": sheet.get("languages", []),
        "equipment": [{"name": i["item"], "quantity": i["quantity"]} for i in sheet.get("inventory", [])],
        "treasure": sheet.get("treasure", {}),
        "features": sheet.get("features", []),
        "spellcasting": _spellcasting(sheet),
    }
    if seed is not None or request is not None:
        out["meta"] = {"seed": seed, "request": request}
    return out
