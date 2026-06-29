"""Derivation orchestrator: full-sheet assembly + cross-module multiclass behaviour through derive()."""
import pytest

from app.derivation import derive


def test_derive_rejects_empty_classes(catalog):
    with pytest.raises(ValueError, match="at least one class"):
        derive(catalog, {"classes": []})


def test_multiclass_saves_come_from_primary_class_only(catalog):
    choices = {"race": "Human", "classes": [{"class": "Warrior", "level": 2}, {"class": "Mage", "level": 3}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 12, "wis": 10, "cha": 8}}
    sheet = derive(catalog, choices)
    assert sheet["level"] == 5 and sheet["proficiency_bonus"] == 3      # total level drives prof bonus
    assert sheet["saving_throws"]["str"]["proficient"] is True          # warrior (primary)
    assert sheet["saving_throws"]["int"]["proficient"] is False         # mage's save NOT granted (secondary)


def test_passive_perception_through_derive(catalog):
    choices = {"race": "Human", "classes": [{"class": "Mage", "level": 5}], "skill_choices": ["Perception"],
               "ability_assignment": {"str": 8, "dex": 10, "con": 12, "int": 13, "wis": 14, "cha": 10}}
    assert derive(catalog, choices)["passive_perception"] == 15


def test_derive_full_sheet_smoke(catalog):
    choices = {"race": "Human", "classes": [{"class": "Mage", "level": 5, "subclass": "Evoker"}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10},
               "skill_choices": ["Lore", "Runes"],
               "spell_choices": {"cantrips": ["Spark"], "spells": ["Bolt"]}}
    sheet = derive(catalog, choices)
    assert sheet["level"] == 5 and sheet["proficiency_bonus"] == 3
    assert sheet["ability_scores"]["int"] == 18 and sheet["ability_modifiers"]["int"] == 4  # 15+1 race +2 ASI
    assert sheet["max_hp"] == 32        # (6+2) + 4×(4+2)
    assert sheet["speed"] == 30 and sheet["initiative"] == sheet["ability_modifiers"]["dex"]
    assert sheet["spellcasting"]["Mage"]["save_dc"] == 15
    assert sheet["spell_slots"] == {1: 4, 2: 3, 3: 2}
    assert sheet["languages"][0] == "Common"
    assert sheet["schema_version"] == 1 and sheet["death_saves"] == {"successes": 0, "failures": 0}
    assert set(sheet) >= {"saving_throws", "skills", "passive_perception", "hit_dice", "armor_class",
                          "proficiencies", "languages", "features", "spells"}
