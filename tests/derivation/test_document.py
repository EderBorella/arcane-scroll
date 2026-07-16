"""Full-document pipeline (F05-T68, S13 Phase 3) tests — synthetic, content-neutral choices only.

The pipeline (``app.derivation.document.derive_document``) wires the DAL derivers together: a
character's choices → the full five-schema document ``{core, inventory, grimoire?, modifier,
companion?}``. The primary acceptance check is that EACH schema of the generated document passes its
own validator.

The default build's species (``species-a``) carries an always-on ability-set grant (``gas-species-a``
SETs ability a2 to 20 — a NON-item owner). That is reconciliation debt (b): the MODIFIER deriver
historically applied ``grant_ability_set`` only over a state-driven owner set + attuned items, while
the validator re-derives ability sets from the permanent owners (species/feats/classes/subclasses)
too. So a document built from this build must apply the species set to its effective abilities, or it
trips a false ``effective-ability-mismatch``. These tests pin that reconciliation.

All ids are synthetic placeholders from the shared rules-DB fixture (``class-a``, ``species-a``,
``sub-ek`` …) — never real game vocabulary.
"""
import pytest

from app.derivation.document import assemble_inventory, derive_document
from validator.validate_core import validate_core
from validator.validate_grimoire import validate_grimoire
from validator.validate_inventory import validate_inventory
from validator.validate_modifier import validate_modifier


def _noncaster_choices():
    """A single-class level-3 build with a subclass (mirrors the CORE deriver's fixture)."""
    return {
        "character_id": "char-1",
        "character_name": "Test Character",
        "species": "species-a",
        "size": "size-a",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8, "wisdom": 10},
        "background_increase": {"a1": 2, "a2": 1},
        "skills": ["sk1", "sk2"],
        "feats": [],
        "languages": [],
    }


def _caster_choices():
    """A build whose subclass casts (``sub-ek`` on ``class-m`` carries subclass_spellcasting) → a
    GRIMOIRE sheet. sub-ek unlocks its casting at level 3."""
    choices = _noncaster_choices()
    choices["character_id"] = "char-2"
    choices["classes"] = [{"class": "class-m", "level": 3, "subclass": "sub-ek"}]
    # class-m carries no explicit skill pool; keep only the auto-granted background/species skills.
    choices["skills"] = []
    return choices


def _innate_only_choices():
    """A NON-caster class (``class-m`` below its subclass unlock) whose only spell source is the
    species innate cantrip (``species-a`` grants one). This is NOT a class spellcasting progression,
    so the document must carry NO GRIMOIRE — matching the corpus, which reserves grimoire sheets for
    class casters."""
    choices = _noncaster_choices()
    choices["character_id"] = "char-innate"
    choices["classes"] = [{"class": "class-m", "level": 2, "subclass": None}]
    choices["skills"] = []
    return choices


def _equipped_choices():
    """The non-caster build, now holding a couple of items — exercises the INVENTORY assembly and
    MODIFIER's inventory-aware layer (equipped items feed the effect resolution). Uses concrete
    synthetic catalog items so the inventory validator resolves each name."""
    choices = _noncaster_choices()
    choices["equipment"] = {
        "equipped": {"main_hand": {"name": "Blade Alpha"}},
        "backpack": ["Leather Armor", {"name": "Magic Scroll", "quantity": 3}],
    }
    return choices


@pytest.fixture
def document(gen_access):
    return derive_document(_noncaster_choices(), gen_access)


# --------------------------------------------------------------------------- acceptance: every schema

def test_document_has_required_schemas(document):
    assert set(document) >= {"core", "inventory", "modifier"}


def test_core_passes_validator(document, access):
    report = validate_core(document["core"], access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


def test_inventory_passes_validator(document, access):
    report = validate_inventory(document["core"], document["inventory"],
                                document.get("modifier"), access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


def test_modifier_passes_validator(document, access):
    # This is the debt-(b) acceptance: the deriver must apply the species always-on ability set so
    # effective abilities agree with the validator's independent owner re-derivation.
    report = validate_modifier(document["core"], document.get("inventory"),
                               document.get("grimoire"), document["modifier"], access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


# --------------------------------------------------------------------------- reconciliation debt (b)

def test_species_always_on_ability_set_applied_to_effective(document):
    # species-a SETs a2 to 20 (an always-on, non-item grant). CORE keeps a2 at base+background (14);
    # MODIFIER's effective_abilities must reflect the override (20) — the deriver/validator agreement.
    assert document["core"]["abilities"]["x2"]["final"] == 14
    assert document["modifier"]["effective_abilities"]["x2"] == 20


# --------------------------------------------------------------------------- caster build → GRIMOIRE

def test_caster_document_includes_grimoire(gen_access):
    document = derive_document(_caster_choices(), gen_access)
    assert "grimoire" in document
    assert document["grimoire"]["schema_version"] == 1


def test_species_innate_spell_only_produces_no_grimoire(gen_access):
    # An innate species cantrip is not a CLASS spellcasting progression → no GRIMOIRE sheet, even
    # though the build technically has a spell source.
    document = derive_document(_innate_only_choices(), gen_access)
    assert "grimoire" not in document


def test_caster_all_schemas_pass(gen_access, access):
    document = derive_document(_caster_choices(), gen_access)
    assert validate_core(document["core"], access)["legal"] is True
    assert validate_inventory(document["core"], document["inventory"],
                              document.get("modifier"), access)["legal"] is True
    assert validate_grimoire(document["core"], document["grimoire"], access)["legal"] is True
    assert validate_modifier(document["core"], document.get("inventory"),
                             document["grimoire"], document["modifier"], access)["legal"] is True


# --------------------------------------------------------------------------- INVENTORY assembly

def test_empty_equipment_yields_legal_empty_inventory(gen_access, access):
    document = derive_document(_noncaster_choices(), gen_access)
    inv = document["inventory"]
    assert inv["equipped"] == {}
    assert inv["backpack"] == []
    report = validate_inventory(document["core"], inv, document.get("modifier"), access)
    assert report["legal"] is True, report["violations"]


def test_assembled_items_get_unique_ids(gen_access):
    choices = _equipped_choices()
    core = derive_document(choices, gen_access)["core"]
    inv = assemble_inventory(choices, core, gen_access)
    ids = [inv["equipped"]["main_hand"]["id"]] + [i["id"] for i in inv["backpack"]]
    assert len(ids) == len(set(ids)), f"duplicate item ids: {ids}"
    assert inv["backpack"][1]["quantity"] == 3


def test_equipped_document_all_schemas_pass(gen_access, access):
    document = derive_document(_equipped_choices(), gen_access)
    assert validate_core(document["core"], access)["legal"] is True
    report = validate_inventory(document["core"], document["inventory"],
                                document.get("modifier"), access)
    assert report["legal"] is True, report["violations"]
    report = validate_modifier(document["core"], document["inventory"],
                               document.get("grimoire"), document["modifier"], access)
    assert report["legal"] is True, report["violations"]


# --------------------------------------------------------------------------- no companion → omitted

def test_document_without_companions_omits_companion(document):
    assert "companion" not in document
