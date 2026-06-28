"""Derivation engine: proficiency bonus, ability scores (race + ASI), HP, AC, saves, skills, spell
stats, speed — and a full-sheet smoke test."""
from app.derivation import engine, derive


def _scores(**over):
    s = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    s.update(over)
    return s


def test_proficiency_bonus():
    assert [engine.proficiency_bonus(n) for n in (1, 4, 5, 9, 13, 17, 20)] == [2, 2, 3, 4, 5, 6, 6]


def test_ability_scores_apply_race_and_asi(catalog):
    choices = {"race": "Human", "feat": "Ability Score Improvement: Intelligence",
               "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10}}
    s = engine.ability_scores(catalog, choices)
    assert s["int"] == 18           # 15 base + 1 (human racial) + 2 (ASI pick)
    assert s["str"] == 8


def test_reserved_asi_goes_to_primary_ability(catalog):
    choices = {"race": "Human", "feat": ["FeatA", "FeatB"],          # 2 real feats, 3 slots → 1 reserved ASI
               "classes": [{"class": "Fighter", "level": 8}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    s = engine.ability_scores(catalog, choices)
    assert s["str"] == 17           # fighter's primary ability gets the reserved +2


def test_ability_scores_cap_at_20(catalog):
    choices = {"race": "Human", "feat": "Ability Score Improvement: Intelligence",
               "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 19, "wis": 12, "cha": 10}}
    assert engine.ability_scores(catalog, choices)["int"] == 20       # 19+1+2 clamped


def test_max_hp_and_hit_dice(catalog):
    assert engine.max_hp(catalog, [("warrior", 3)], 2) == 28          # (10+2) + (6+2) + (6+2)
    assert engine.hit_dice(catalog, [("warrior", 3), ("mage", 2)]) == {"d10": 3, "d6": 2}


def test_armor_class_unarmored_and_defences(catalog):
    assert engine.armor_class(catalog, _scores(dex=16), [("mage", 5)]) == 13          # 10 + DEX
    assert engine.armor_class(catalog, _scores(dex=14, con=16), [("barbarian", 3)]) == 15  # +CON
    assert engine.armor_class(catalog, _scores(dex=14, wis=16), [("monk", 3)]) == 15       # +WIS


def test_saving_throws(catalog):
    st = engine.saving_throws(catalog, _scores(str=16, con=12, dex=14), 2, "warrior")
    assert st["str"] == {"modifier": 5, "proficient": True}           # +3 mod + 2 prof
    assert st["dex"] == {"modifier": 2, "proficient": False}


def test_skill_table_with_expertise(catalog):
    skills = engine.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Lore"], "expertise": ["Lore"]})
    assert skills["Lore"] == {"modifier": 6, "ability": "int", "proficient": True, "expertise": True}  # 2 +2 +2
    assert skills["Runes"]["modifier"] == 2 and not skills["Runes"]["proficient"]


def test_spell_stats(catalog):
    out = engine.spell_stats(catalog, _scores(int=18), 3, [("mage", 5)])
    assert out["Mage"] == {"ability": "int", "save_dc": 15, "attack_bonus": 7}
    assert engine.spell_stats(catalog, _scores(), 2, [("warrior", 3)]) == {}   # non-caster


def test_race_speed(catalog):
    assert engine._race_speed(catalog, "Human") == 30
    assert engine._race_speed(catalog, "Unknownfolk") == 30          # generic fallback


def test_one_feat_slot_picking_a_feat_bumps_nothing(catalog):
    choices = {"race": "Human", "feat": "FeatA", "classes": [{"class": "Mage", "level": 4}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10}}
    assert engine.ability_scores(catalog, choices)["int"] == 16        # 15 + racial only, no ASI

def test_multiclass_asi_slots_are_summed(catalog):
    choices = {"race": "Human", "classes": [{"class": "Fighter", "level": 4}, {"class": "Rogue", "level": 4}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8}}
    # 1 slot from each class, no feat picks → 2 reserved ASIs, both on the primary (fighter → str)
    assert engine.ability_scores(catalog, choices)["str"] == 19

def test_multiclass_hp_only_first_level_is_maxed(catalog):
    # primary = mage (d6) maxed at L1; every later level averages (mage d6→4, warrior d10→6); +1 CON each
    assert engine.max_hp(catalog, [("mage", 3), ("warrior", 2)], 1) == 31

def test_multiclass_saves_come_from_primary_class_only(catalog):
    choices = {"race": "Human", "classes": [{"class": "Warrior", "level": 2}, {"class": "Mage", "level": 3}],
               "ability_assignment": {"str": 15, "dex": 13, "con": 14, "int": 12, "wis": 10, "cha": 8}}
    sheet = derive(catalog, choices)
    assert sheet["level"] == 5 and sheet["proficiency_bonus"] == 3     # total level drives prof bonus
    assert sheet["saving_throws"]["str"]["proficient"] is True         # warrior (primary)
    assert sheet["saving_throws"]["int"]["proficient"] is False        # mage's save NOT granted (secondary)

def test_multiclass_two_casters_each_get_spell_stats(catalog):
    out = engine.spell_stats(catalog, _scores(int=18, wis=14), 3, [("mage", 5), ("oracle", 3)])
    assert out["Mage"]["save_dc"] == 15 and out["Oracle"]["save_dc"] == 13   # int vs wis casters

def test_passive_perception_uses_the_perception_skill(catalog):
    choices = {"race": "Human", "classes": [{"class": "Mage", "level": 5}], "skill_choices": ["Perception"],
               "ability_assignment": {"str": 8, "dex": 10, "con": 12, "int": 13, "wis": 14, "cha": 10}}
    # WIS +2, proficient (+3 at L5) → Perception 5 → passive 15
    assert derive(catalog, choices)["passive_perception"] == 15

def test_negative_modifiers_propagate(catalog):
    skills = engine.skill_table(catalog, _scores(str=8), 2, {"skill_choices": ["Brawn"]})
    assert skills["Brawn"]["modifier"] == 1                            # -1 (STR 8) + 2 prof
    st = engine.saving_throws(catalog, _scores(str=8, con=10), 2, "warrior")
    assert st["str"]["modifier"] == 1                                  # -1 + 2 prof
    assert st["dex"]["modifier"] == 0                                  # mod 0, not proficient

def test_proficient_without_expertise(catalog):
    skills = engine.skill_table(catalog, _scores(int=14), 2, {"skill_choices": ["Runes"]})
    assert skills["Runes"] == {"modifier": 4, "ability": "int", "proficient": True, "expertise": False}

def test_derive_full_sheet_smoke(catalog):
    choices = {"race": "Human", "classes": [{"class": "Mage", "level": 5, "subclass": "Evoker"}],
               "ability_assignment": {"str": 8, "dex": 13, "con": 14, "int": 15, "wis": 12, "cha": 10},
               "skill_choices": ["Lore", "Runes"],
               "spell_choices": {"cantrips": ["Spark"], "spells": ["Bolt"]}}
    sheet = derive(catalog, choices)
    assert sheet["level"] == 5 and sheet["proficiency_bonus"] == 3
    assert sheet["ability_scores"]["int"] == 18 and sheet["ability_modifiers"]["int"] == 4  # 15+1 race +2 ASI
    assert sheet["max_hp"] == 32        # (6+2) + 4×(4+2), CON mod +2
    assert sheet["speed"] == 30 and sheet["initiative"] == sheet["ability_modifiers"]["dex"]
    assert sheet["spellcasting"]["Mage"]["save_dc"] == 15
    assert set(sheet) >= {"saving_throws", "skills", "passive_perception", "hit_dice", "armor_class"}
