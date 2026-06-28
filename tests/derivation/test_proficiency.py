"""Proficiency-derived stats: prof bonus, saves (primary-only), skills + expertise, passive perception."""
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


def test_negative_modifiers_propagate(catalog):
    skills = proficiency.skill_table(catalog, _scores(str=8), 2, {"skill_choices": ["Brawn"]})
    assert skills["Brawn"]["modifier"] == 1                        # -1 (STR 8) + 2 prof
    st = proficiency.saving_throws(catalog, _scores(str=8, con=10), 2, "warrior")
    assert st["str"]["modifier"] == 1 and st["dex"]["modifier"] == 0


def test_skill_table_with_expertise(catalog):
    skills = proficiency.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Lore"], "expertise": ["Lore"]})
    assert skills["Lore"] == {"modifier": 6, "ability": "int", "proficient": True, "expertise": True}  # 2+2+2
    assert skills["Runes"]["modifier"] == 2 and not skills["Runes"]["proficient"]


def test_proficient_without_expertise(catalog):
    skills = proficiency.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Runes"]})
    assert skills["Runes"] == {"modifier": 4, "ability": "int", "proficient": True, "expertise": False}


def test_passive_perception(catalog):
    skills = proficiency.skill_table(catalog, _scores(wis=14), 3, {"skill_choices": ["Perception"]})
    assert proficiency.passive_perception(skills) == 15           # 10 + (WIS +2, prof +3)
