"""Proficiency-derived stats: prof bonus, saves (primary-only), skills + expertise + sources,
passive perception, proficiencies, and languages."""
import random

from app.derivation import proficiency


def _scores(**over):
    s = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    s.update(over)
    return s


def test_proficiency_bonus():
    assert [proficiency.proficiency_bonus(n) for n in (1, 4, 5, 9, 13, 17, 20)] == [2, 2, 3, 4, 5, 6, 6]


def test_saving_throws(catalog):
    st = proficiency.saving_throws(catalog, _scores(str=16, con=12, dex=14), 2, "warrior")
    assert st["str"] == {"modifier": 5, "proficient": True}        # +3 mod + 2 prof
    assert st["dex"] == {"modifier": 2, "proficient": False}


def test_unknown_class_index_does_not_crash(catalog):
    # an unrecognised primary class must degrade (no proficiencies) rather than AttributeError
    st = proficiency.saving_throws(catalog, _scores(), 2, "nonexistent")
    assert all(not v["proficient"] for v in st.values())
    assert proficiency.proficiencies(catalog, [("nonexistent", 1)]) == {"armor": [], "weapons": [], "tools": []}


def test_negative_modifiers_propagate(catalog):
    skills = proficiency.skill_table(catalog, _scores(str=8), 2, {"skill_choices": ["Brawn"]})
    assert skills["Brawn"]["modifier"] == 1                        # -1 (STR 8) + 2 prof
    st = proficiency.saving_throws(catalog, _scores(str=8, con=10), 2, "warrior")
    assert st["str"]["modifier"] == 1 and st["dex"]["modifier"] == 0


def test_skill_table_with_expertise(catalog):
    skills = proficiency.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Lore"], "expertise": ["Lore"]})
    assert skills["Lore"] == {"modifier": 6, "ability": "int", "proficient": True,
                              "expertise": True, "source": "class"}      # 2 +2 +2
    assert skills["Runes"]["modifier"] == 2 and skills["Runes"]["source"] is None


def test_proficient_without_expertise(catalog):
    skills = proficiency.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Runes"]})
    assert skills["Runes"] == {"modifier": 4, "ability": "int", "proficient": True,
                               "expertise": False, "source": "class"}


def test_background_grants_skills_with_source(catalog):
    skills = proficiency.skill_table(catalog, _scores(int=14), 2, {"background": "Scholar"})
    assert skills["Lore"]["proficient"] and skills["Lore"]["source"] == "background"
    assert skills["Runes"]["source"] == "background"
    assert skills["Brawn"]["source"] is None


def test_proficiencies_armor_weapons_and_background_tools(catalog):
    p = proficiency.proficiencies(catalog, [("fighter", 5)], "Scholar")
    assert "All armor" in p["armor"] and "Shields" in p["armor"]
    assert "Simple weapons" in p["weapons"] and "Martial weapons" in p["weapons"]
    assert p["tools"] == ["Quill"]


def test_languages_common_race_and_background(catalog):
    langs = proficiency.languages(catalog, "Human", "Scholar", random.Random(0))
    assert langs[0] == "Common"
    assert len(langs) == 3 and len(set(langs)) == 3          # Common + 1 race option + 1 background pick
    assert any(l in {"LangA", "LangB"} for l in langs)       # the race option came from its inline list


def test_languages_no_background_extras(catalog):
    langs = proficiency.languages(catalog, "Human", "Outcast", random.Random(1))
    assert langs[0] == "Common" and len(langs) == 2          # Common + 1 race option; Outcast grants 0


def test_passive_perception(catalog):
    skills = proficiency.skill_table(catalog, _scores(wis=14), 3, {"skill_choices": ["Perception"]})
    assert proficiency.passive_perception(skills) == 15           # 10 + (WIS +2, prof +3)
