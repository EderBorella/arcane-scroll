"""Tests for the C-M1 MODIFIER derivation engine."""
from app.derivation.modifier import (
    ActiveEffects, resolve_active_effects,
    derive_abilities, derive_ac, derive_speed, derive_defenses, derive_size,
    derive_saving_throws, derive_skills, derive_passive_scores,
    derive_initiative, derive_hp_effects, derive_resource_state,
    derive_prepared_spells, derive_attacks, derive_senses,
    derive_features, derive_feats,
)


def _core(**overrides):
    sheet = {
        "identity": {
            "name": "Test", "species": "Species A",
            "size": "medium", "creature_type": "Type A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {
            "a1": {"final": 14},   # Strength
            "a2": {"final": 16},   # Dexterity
            "a3": {"final": 12},   # Constitution
        },
        "proficiency_bonus": 2,
        "saving_throws": {"a1": True, "a2": False, "a3": True},
        "skills": {
            "sk1": {"ability": "a1", "proficient": True, "expertise": False},
            "sk2": {"ability": "a2", "proficient": False, "expertise": False},
            "sk3": {"ability": "a1", "proficient": True, "expertise": True},
        },
        "permanent_senses": {"darkvision": 60},
        "permanent_speed": {"walk": 30},
        "permanent_defenses": {
            "resistances": ["fire"], "immunities": [], "vulnerabilities": [],
            "condition_immunities": ["charmed"],
            "save_advantages": ["a1"], "condition_advantages": [],
        },
        "proficiencies": {"armor": [], "weapons": ["simple", "martial"], "tools": []},
        "weapon_masteries": [],
        "features": [{"name": "Feat A", "source": "class-a"}],
        "feats": [{"name": "feat-gen", "source": "bg-a"}],
        "resource_budgets": {},
        "hit_points": {"max": 22},
        "languages": [], "flavour": None,
    }
    sheet.update(overrides)
    return sheet


def _empty_effects():
    return ActiveEffects()


# ── derive_abilities ─────────────────────────────────────────────────────────


def test_derive_abilities_baseline(access):
    core = _core()
    abilities, effective, mods = derive_abilities(core, _empty_effects(), access)
    assert abilities["a1"]["modifier"] == 2   # floor((14-10)/2) = 2
    assert abilities["a2"]["modifier"] == 3   # floor((16-10)/2) = 3
    assert abilities["a1"]["reduction"] == 0
    assert effective["a1"] == 14
    assert effective["a2"] == 16


def test_derive_abilities_set_item(access):
    core = _core()
    effects = ActiveEffects()
    effects.ability_sets.append({"ability_id": "a1", "score": 19, "mode": "set"})
    abilities, effective, mods = derive_abilities(core, effects, access)
    assert effective["a1"] == 19
    assert abilities["a1"]["modifier"] == 4  # floor((19-10)/2)


# ── derive_ac ────────────────────────────────────────────────────────────────


def test_derive_ac_unarmored(access):
    core = _core()
    abilities = {"dexterity": 3, "strength": 2, "constitution": 1}
    ac, detail = derive_ac(core, None, _empty_effects(), abilities, access)
    assert ac == 13  # 10 + 3 Dex
    assert detail["source"] == "unarmored"


def test_derive_ac_worn_armor(access):
    core = _core()
    inventory = {"equipped": {"armor": {"id": "a1", "name": "Chain Mail"}}}
    abilities = {"dexterity": 3}
    ac, detail = derive_ac(core, inventory, _empty_effects(), abilities, access)
    assert ac == 16  # 16 base + 0 Dex (heavy, cap=0)
    assert detail["dex_bonus"] == 0


def test_derive_ac_with_shield(access):
    core = _core()
    inventory = {
        "equipped": {
            "armor": {"id": "a1", "name": "Leather Armor"},
            "shield": {"id": "s1", "name": "Shield"},
        }
    }
    abilities = {"dexterity": 3}
    ac, detail = derive_ac(core, inventory, _empty_effects(), abilities, access)
    assert ac == 16  # 11 base + 3 Dex (light, uncapped) + 2 shield
    assert detail["dex_bonus"] == 3


def test_derive_ac_spell_bonus(access):
    core = _core()
    abilities = {"dexterity": 2}
    effects = ActiveEffects()
    effects.bonuses.append({"target_kind": "ac", "value": 2, "source_name": "shield-of-faith"})
    ac, detail = derive_ac(core, None, effects, abilities, access)
    assert ac == 14  # 10 + 2 Dex + 2 spell
    assert len(detail["bonuses"]) == 1
    assert detail["bonuses"][0]["value"] == 2


def test_derive_ac_floor(access):
    core = _core()
    abilities = {"dexterity": 1}
    effects = ActiveEffects()
    effects.ac_floor = 16
    ac, detail = derive_ac(core, None, effects, abilities, access)
    assert ac == 16  # max(10+1, floor=16)
    assert detail["floor"] == 16


# ── derive_speed ─────────────────────────────────────────────────────────────


def test_derive_speed_baseline(access):
    core = _core()
    speeds, detail = derive_speed(core, _empty_effects(), access)
    assert speeds["walk"] == 30
    assert detail["base"] == 30


# ── derive_defenses ──────────────────────────────────────────────────────────


def test_derive_defenses_baseline(access):
    core = _core()
    defenses = derive_defenses(core, _empty_effects(), access)
    assert "fire" in defenses["resistances"]
    assert "charmed" in defenses["condition_immunities"]


def test_derive_defenses_state_grants(access):
    core = _core()
    effects = ActiveEffects()
    effects.resistances.add("cold")
    effects.condition_immunities.add("frightened")
    defenses = derive_defenses(core, effects, access)
    assert "cold" in defenses["resistances"]
    assert "frightened" in defenses["condition_immunities"]


# ── derive_size ──────────────────────────────────────────────────────────────


def test_derive_size_default(access):
    core = _core()
    assert derive_size(core, _empty_effects(), access) == "medium"


# ── derive_saving_throws ─────────────────────────────────────────────────────


def test_derive_saving_throws(access):
    core = _core()
    abilities = {"a1": 2, "a2": 3, "a3": 1}
    saves = derive_saving_throws(core, abilities, 2, _empty_effects(), access)
    assert saves["a1"]["modifier"] == 4  # 2 + PB(2) proficient
    assert saves["a2"]["modifier"] == 3  # 3 + 0 not proficient
    assert saves["a3"]["modifier"] == 3  # 1 + PB(2) proficient


def test_derive_saving_throws_bonus(access):
    core = _core()
    abilities = {"a1": 2}
    effects = ActiveEffects()
    effects.bonuses.append({"target_kind": "saving_throw", "value": 1, "ability_id": None,
                            "source_name": "bless"})
    saves = derive_saving_throws(core, abilities, 2, effects, access)
    assert saves["a1"]["modifier"] == 5  # 2 + PB(2) + 1 bonus


# ── derive_skills ────────────────────────────────────────────────────────────


def test_derive_skills(access):
    core = _core()
    abilities = {"a1": 2, "a2": 3}
    skills = derive_skills(core, abilities, 2, _empty_effects(), access)
    assert skills["sk1"]["modifier"] == 4  # 2 + PB(2) proficient
    assert skills["sk2"]["modifier"] == 3  # 3 + 0 not proficient
    assert skills["sk3"]["modifier"] == 6  # 2 + PB(2)*2 expertise


# ── derive_passive_scores ────────────────────────────────────────────────────


def test_derive_passive_scores(access):
    core = _core()
    abilities = {"a1": 2, "a2": 3}
    skills = derive_skills(core, abilities, 2, _empty_effects(), access)
    passives = derive_passive_scores(core, skills, _empty_effects(), access)
    assert passives["sk1"] == 14  # 10 + 4


# ── derive_initiative ────────────────────────────────────────────────────────


def test_derive_initiative(access):
    abilities = {"dexterity": 3}
    assert derive_initiative({}, abilities, 2, _empty_effects(), access) == 3


# ── derive_hp_effects ────────────────────────────────────────────────────────


def test_derive_hp_effects_baseline(access):
    hp = derive_hp_effects(_core(), _empty_effects(), access)
    assert hp["max_boost"] == 0
    assert hp["max_reduction"] == 0


# ── derive_resource_state ────────────────────────────────────────────────────


def test_derive_resource_state(access):
    core = _core()
    core["resource_budgets"] = {"rage": {"max": 3}}
    state = derive_resource_state(core, _empty_effects(), access)
    assert state["rage"]["max"] == 3


# ── derive_prepared_spells ───────────────────────────────────────────────────


def test_derive_prepared_spells(access):
    grimoire = {
        "spells": [
            {"name": "Sp3", "source": "class:class-a", "bucket": "prepared"},
            {"name": "Sp1", "source": "class:class-a", "bucket": "cantrip"},
        ]
    }
    result = derive_prepared_spells(grimoire, access)
    assert len(result) == 1
    assert "Sp3|class:class-a" in result


def test_derive_prepared_spells_none(access):
    assert derive_prepared_spells(None, access) == []


# ── derive_attacks ───────────────────────────────────────────────────────────


def test_derive_attacks_melee(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Greataxe"}}}
    abilities = {"strength": 2, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert len(attacks) == 1
    a = attacks[0]
    assert a["name"] == "Greataxe"
    assert a["attack_bonus"] == 4  # 2 Str + 2 PB
    assert "d12" in a["damage"]
    assert "two-handed" in a["properties"]


def test_derive_attacks_finesse(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w2", "name": "Club"}}}
    abilities = {"strength": 1, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert len(attacks) == 1
    # Club has no finesse, so it's melee (Str)
    assert attacks[0]["attack_bonus"] == 3  # 1 Str + 2 PB


def test_derive_attacks_bonus(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Greataxe"}}}
    abilities = {"strength": 2}
    effects = ActiveEffects()
    effects.bonuses.append({"target_kind": "weapon_attack", "value": 1,
                            "source_name": "magic-weapon"})
    attacks = derive_attacks(core, inventory, abilities, [], effects, access)
    assert attacks[0]["attack_bonus"] == 5  # 2 Str + 2 PB + 1 bonus


def test_derive_attacks_no_weapon(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Nonexistent"}}}
    attacks = derive_attacks(core, inventory, {"strength": 2}, [], _empty_effects(), access)
    assert attacks == []


# ── derive_senses ────────────────────────────────────────────────────────────


def test_derive_senses_baseline(access):
    core = _core()
    senses = derive_senses(core, _empty_effects(), access)
    assert senses["darkvision"] == 60


# ── derive_features / derive_feats ───────────────────────────────────────────


def test_derive_features(access):
    core = _core()
    features = derive_features(core, access)
    assert len(features) == 1
    assert features[0]["name"] == "Feat A"
    assert "uses" in features[0]


def test_derive_feats(access):
    core = _core()
    feats = derive_feats(core, access)
    assert len(feats) == 1
    assert feats[0]["name"] == "feat-gen"


# ── resolve_active_effects ───────────────────────────────────────────────────


def test_resolve_empty_states(access):
    effects = resolve_active_effects(_core(), None, [], [], access)
    assert effects.bonuses == []
    assert effects.resistances == set()


def test_resolve_empty_returns_effects(access):
    effects = resolve_active_effects(_core(), None, [], [], access)
    assert isinstance(effects, ActiveEffects)
    assert effects.hp_boost == 0


# ── smoke ────────────────────────────────────────────────────────────────────


def test_empty_state_defaults(access):
    core = _core()
    effects = _empty_effects()
    abilities, eff, mods = derive_abilities(core, effects, access)

    ac, _ = derive_ac(core, None, effects, {"dexterity": 2}, access)
    defenses = derive_defenses(core, effects, access)
    size = derive_size(core, effects, access)
    saves = derive_saving_throws(core, mods, 2, effects, access)
    skills = derive_skills(core, mods, 2, effects, access)
    passives = derive_passive_scores(core, skills, effects, access)
    init = derive_initiative(core, mods, 2, effects, access)
    hp = derive_hp_effects(core, effects, access)
    res = derive_resource_state(core, effects, access)
    spells = derive_prepared_spells(None, access)
    senses = derive_senses(core, effects, access)
    feat_uses = derive_features(core, access)
    feat_list_uses = derive_feats(core, access)

    assert abilities["a1"]["modifier"] == 2
    assert ac == 12  # 10 + 2
    assert "fire" in defenses["resistances"]
    assert size == "medium"
    assert hp["max_boost"] == 0
    assert isinstance(feat_uses, list)
    assert isinstance(feat_list_uses, list)
