"""T14 — ``derive_document`` tolerates a MINIMAL core (F07 D5).

The choice-bearing inputs (``equipment`` / ``spells`` / ``treasure`` / ``starting_equipment``) are all
optional. Given only the build fundamentals (species / background / class / subclass / level) the
pipeline derives everything derivable and leaves each absent choice EMPTY — never defaulted or
invented — for the completeness manifest to flag. Full-input derivation stays unchanged.

Synthetic content-neutral ids only (``species-a``, ``class-a``, ``sub-a`` …).
"""
from engine.derivation.document import derive_document


def _minimal():
    """Only the build fundamentals — no equipment / spells / treasure / starting_equipment."""
    return {
        "character_id": "char-min",
        "character_name": "Min",
        "species": "species-a",
        "classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
        "background": "bg-a",
        "ability_scores": {"a1": 15, "a2": 13, "a3": 14, "a4": 10, "a5": 12, "a6": 8},
    }


def test_minimal_core_derives_all_derivable(gen_access):
    doc = derive_document(_minimal(), gen_access)
    # CORE / INVENTORY / MODIFIER are always present; everything derivable is derived.
    assert {"core", "inventory", "modifier"} <= set(doc)
    assert doc["core"]["identity"]["total_level"] == 3
    assert doc["core"]["proficiency_bonus"] == 2


def test_absent_choices_left_empty_not_invented(gen_access):
    doc = derive_document(_minimal(), gen_access)
    # Absent equipment -> empty inventory (no invented items).
    assert doc["inventory"]["equipped"] == {}
    assert doc["inventory"]["backpack"] == []
    # Absent treasure -> zeroed, not a fabricated purse.
    assert doc["modifier"]["treasure"] == {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}


def test_minimal_core_does_not_raise_without_choice_inputs(gen_access):
    # The four choice-bearing keys are entirely absent; the pipeline must not require them.
    choices = _minimal()
    for key in ("equipment", "spells", "treasure", "starting_equipment"):
        assert key not in choices
    derive_document(choices, gen_access)  # must not raise


def test_full_input_derivation_unchanged(gen_access):
    # The same build WITH equipment + treasure still populates both — the full path is untouched.
    choices = _minimal()
    choices["equipment"] = {"equipped": {"main_hand": {"name": "Weapon A"}}, "backpack": ["Armor B"]}
    choices["treasure"] = {"pp": 0, "gp": 25, "ep": 0, "sp": 0, "cp": 0}
    doc = derive_document(choices, gen_access)
    assert doc["inventory"]["equipped"]["main_hand"]["name"] == "Weapon A"
    assert doc["inventory"]["backpack"][0]["name"] == "Armor B"
    assert doc["modifier"]["treasure"]["gp"] == 25
