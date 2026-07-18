"""Tests for the C-M1 MODIFIER derivation engine."""
from app.derivation.modifier import (
    ActiveEffects, resolve_active_effects,
    derive_abilities, derive_ac, derive_speed, derive_defenses, derive_size,
    derive_saving_throws, derive_skills, derive_passive_scores,
    derive_initiative, derive_hp_effects, derive_resource_state,
    derive_attacks, derive_senses,
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
        "proficiencies": {"armor": [], "weapons": ["simple weapons", "martial weapons"], "tools": []},
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


def _access_with_dex_str(access):
    """Return an access wired to this test's isolated DB after adding real Dexterity/Strength
    abilities (abbrevs Dex/Str). The AC/attack derivers resolve the canonical 'dexterity'/'strength'
    ids, so the synthetic DB (which only has placeholder abilities) needs them present to exercise a
    short-keyed abilities dict. The `access` fixture is function-scoped, so this stays local."""
    import sqlite3
    from access.validator import ValidatorAccess
    con = sqlite3.connect(access.db.path)
    con.execute("INSERT INTO ability VALUES ('dexterity','Dexterity','Dex')")
    con.execute("INSERT INTO ability VALUES ('strength','Strength','Str')")
    con.commit()
    con.close()
    return ValidatorAccess(path=access.db.path)


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
    """Key-mismatch regression: CORE abilities are keyed by the short code (abbrev x1), while the
    set-ability grant's ability_id is the full DB id (a1). The set-score must still apply — the
    deriver normalises the short key to the full id before matching. (Keying CORE by the id, as the
    old fixture did, gave false confidence: the synthetic key equalled the grant's id.)"""
    core = _core(abilities={"x1": {"final": 14}, "x2": {"final": 16}, "x3": {"final": 12}})
    effects = ActiveEffects()
    effects.ability_sets.append({"ability_id": "a1", "score": 19, "mode": "set"})  # grant is full id
    abilities, effective, mods = derive_abilities(core, effects, access)
    assert effective["x1"] == 19               # set-score applied to x1 (x1 normalises to a1)
    assert abilities["x1"]["modifier"] == 4    # floor((19-10)/2) -- NOT 2 (the pre-fix bug dropped it)
    assert effective["x2"] == 16               # the a1-targeted set must NOT leak to x2


def test_derive_abilities_set_is_true_override_below_base(access):
    """`set` mode is a TRUE OVERRIDE, not a floor: an item that sets the score BELOW the base pulls
    the effective score DOWN to the set value. This is where override and the old max() diverge."""
    core = _core(abilities={"x1": {"final": 18}})
    effects = ActiveEffects()
    effects.ability_sets.append({"ability_id": "a1", "score": 12, "mode": "set"})
    abilities, effective, mods = derive_abilities(core, effects, access)
    assert effective["x1"] == 12               # override -- NOT max(18, 12) == 18
    assert abilities["x1"]["modifier"] == 1    # floor((12-10)/2)


def test_derive_abilities_floor_keeps_higher_base(access):
    """`floor` mode is a minimum, not an override: a floor below the base leaves the base intact."""
    core = _core(abilities={"x1": {"final": 18}})
    effects = ActiveEffects()
    effects.ability_sets.append({"ability_id": "a1", "score": 12, "mode": "floor"})
    abilities, effective, mods = derive_abilities(core, effects, access)
    assert effective["x1"] == 18               # floor: max(18, 12) == 18


def test_item_attuned_ability_set_materializes(access):
    """An attuned magic item's grant_ability_set must materialise at MODIFIER: Belt Alpha sets a1
    to 19, so effective a1 overrides the base (14) to 19. Regression for the attuned-branch call."""
    core = _core()
    inventory = {"equipped": {"waist": {"id": "item-waist", "name": "Belt Alpha"}}}
    item_states = [{"inventory_ref": "item-waist", "attuned": True}]
    effects = resolve_active_effects(core, inventory, [], item_states, access)
    abilities, effective, mods = derive_abilities(core, effects, access)
    assert effective["a1"] == 19               # set by the attuned item (base 14 overridden)
    assert abilities["a1"]["modifier"] == 4    # floor((19-10)/2)


# ── derive_ac ────────────────────────────────────────────────────────────────


def test_derive_ac_unarmored(access):
    core = _core()
    abilities = {"dexterity": 3, "strength": 2, "constitution": 1}
    ac, detail = derive_ac(core, None, _empty_effects(), abilities, access)
    assert ac == 13  # 10 + 3 Dex
    assert detail["source"] == "unarmored"


def test_derive_ac_worn_armor(access):
    core = _core()
    inventory = {"equipped": {"armor": {"id": "a1", "name": "Armor A"}}}
    abilities = {"dexterity": 3}
    ac, detail = derive_ac(core, inventory, _empty_effects(), abilities, access)
    assert ac == 16  # 16 base + 0 Dex (heavy, cap=0)
    assert detail["dex_bonus"] == 0


def test_derive_ac_with_shield(access):
    core = _core()
    inventory = {
        "equipped": {
            "armor": {"id": "a1", "name": "Armor B"},
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
    effects.bonuses.append({"target_kind": "ac", "value": 2, "source_name": "src-spell-a"})
    ac, detail = derive_ac(core, None, effects, abilities, access)
    assert ac == 14  # 10 + 2 Dex + 2 spell
    assert len(detail["bonuses"]) == 1
    assert detail["bonuses"][0]["value"] == 2


def test_derive_ac_short_keyed_abilities_uses_real_dex_mod(access):
    """Folded regression: the deriver's abilities dict is keyed by CORE short codes (the Dex
    abbrev), but derive_ac looks up the full 'dexterity' id. Before the fix that lookup missed and
    Dex silently contributed 0 to AC. With a short-keyed dict the real Dex mod must now reach
    unarmored AC."""
    access = _access_with_dex_str(access)
    core = _core()
    abilities = {"str": 2, "dex": 3}   # keyed by the abbreviations (CORE short codes)
    ac, detail = derive_ac(core, None, _empty_effects(), abilities, access)
    assert ac == 13            # 10 + Dex(3) -- NOT 10 (the pre-fix bug dropped Dex to 0)
    assert detail["dex_bonus"] == 3


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


# ── state-gated resistance materialization (T44b) ─────────────────────────────


def _feature_state(source="State Feature A"):
    return {"state": "active-a", "source": source, "source_type": "feature"}


def test_state_resistance_materializes_only_when_active(access):
    """A condition-gated resistance owned by a class feature materialises when the
    state is active, and stays absent when no state is present."""
    core = _core()
    # No state → the gated resistance does not appear.
    empty = resolve_active_effects(core, None, [], [], access)
    assert "cold" not in empty.resistances
    # State active → the class feature's gated resistance materialises.
    effects = resolve_active_effects(core, None, [_feature_state()], [], access)
    assert "cold" in effects.resistances


def test_state_save_advantage_emitted_as_abbrev_no_dup(access):
    """A state-owned save-advantage grant is recorded as its CORE abbreviation, and the
    derive_defenses union with a CORE abbreviation produces no duplicate."""
    import sqlite3
    con = sqlite3.connect(access.db.path)
    con.execute("INSERT INTO ability VALUES ('dexterity','Dexterity','Dex')")
    con.execute("INSERT INTO grant_save_advantage VALUES "
                "('gsa-state','class_feature','cf-state',NULL,'ability','dexterity',NULL,NULL)")
    con.commit()
    con.close()

    effects = resolve_active_effects(_core(), None, [_feature_state()], [], access)
    assert "Dex" in effects.save_advantages
    assert "dexterity" not in effects.save_advantages  # abbrev, not raw ability_id

    core = _core()
    core["permanent_defenses"]["save_advantages"] = ["Dex"]
    defenses = derive_defenses(core, effects, access)
    assert defenses["save_advantages"].count("Dex") == 1


# ── size step / set / clamp (T44b) ────────────────────────────────────────────


def _grow_state(effect):
    return {"state": "sized", "source": "Spell-Grow", "source_type": "spell",
            "detail": {"effect": effect}}


def test_derive_size_step_up(access):
    core = _core(identity={"size": "size-a"})  # ordinal 3
    effects = resolve_active_effects(core, None, [_grow_state("grow")], [], access)
    assert effects.size_steps == 1
    assert derive_size(core, effects, access) == "size-l"  # ordinal 4


def test_derive_size_step_down(access):
    core = _core(identity={"size": "size-a"})  # ordinal 3
    effects = resolve_active_effects(core, None, [_grow_state("shrink")], [], access)
    assert effects.size_steps == -1
    assert derive_size(core, effects, access) == "size-s"  # ordinal 2


def test_derive_size_step_clamped_at_max(access):
    core = _core(identity={"size": "size-g"})  # ordinal 6 (the max)
    effects = resolve_active_effects(core, None, [_grow_state("grow")], [], access)
    assert derive_size(core, effects, access) == "size-g"  # clamped, no wrap


def test_derive_size_set_from_creature(access):
    """A transformation carrying detail.into sets size absolutely from the creature."""
    core = _core(identity={"size": "size-a"})
    state = {"state": "shaped", "source": "Spell-Grow", "source_type": "spell",
             "detail": {"into": "creat-a"}}
    effects = resolve_active_effects(core, None, [state], [], access)
    assert effects.size_sets == ["size-l"]
    assert derive_size(core, effects, access) == "size-l"


def test_derive_size_set_overrides_step_largest_wins(access):
    """A 'set' target wins over a relative step; on conflict the largest set wins."""
    core = _core(identity={"size": "size-a"})
    effects = ActiveEffects()
    effects.size_steps = -1
    effects.size_sets = ["size-s", "size-h"]  # ordinals 2 and 5
    assert derive_size(core, effects, access) == "size-h"


# ── state-gated extra-damage riders on attacks (T44b) ─────────────────────────


def _inv_weapon_a():
    return {"equipped": {"main_hand": {"id": "w1", "name": "Weapon A"}}}


def _size_state(state_id):
    return {"state": state_id, "source": "Spell-Grow", "source_type": "spell"}


def test_grow_rider_appends_die(access):
    core = _core()
    effects = resolve_active_effects(core, _inv_weapon_a(), [_size_state("grown")], [], access)
    assert {"die_count": 1, "die_faces": 4, "damage_type_id": None} in effects.extra_damage
    attacks = derive_attacks(core, _inv_weapon_a(), {"strength": 2, "dexterity": 3},
                             [], effects, access)
    assert attacks[0]["damage"] == "1d12+2+1d4"


def test_shrink_rider_subtracts_die(access):
    core = _core()
    effects = resolve_active_effects(core, _inv_weapon_a(), [_size_state("shrunk")], [], access)
    assert {"die_count": -1, "die_faces": 4, "damage_type_id": None} in effects.extra_damage
    attacks = derive_attacks(core, _inv_weapon_a(), {"strength": 2, "dexterity": 3},
                             [], effects, access)
    assert attacks[0]["damage"] == "1d12+2-1d4"


def test_rider_gate_no_leak_between_opposite_states(access):
    """The grow rider (gate 'grown') must not fire for the shrunk state, and vice versa."""
    core = _core()
    effects = resolve_active_effects(core, _inv_weapon_a(), [_size_state("grown")], [], access)
    counts = {(x["die_count"], x["die_faces"]) for x in effects.extra_damage}
    assert (1, 4) in counts
    assert (-1, 4) not in counts  # shrink rider gated to 'shrunk' — no leak


def test_no_rider_without_state(access):
    core = _core()
    effects = resolve_active_effects(core, _inv_weapon_a(), [], [], access)
    assert effects.extra_damage == []
    attacks = derive_attacks(core, _inv_weapon_a(), {"strength": 2, "dexterity": 3},
                             [], effects, access)
    assert attacks[0]["damage"] == "1d12+2"


# ── item-owned extra-damage rider on attacks (T51) ────────────────────────────


def _inv_blade():
    return {"equipped": {"main_hand": {"id": "w-main", "name": "Blade Alpha"}}}


def _blade_core():
    return _core(proficiencies={"armor": [], "weapons": ["martial weapons"], "tools": []})


def test_item_rider_folds_into_owning_attack_when_attuned(access):
    core = _blade_core()
    item_states = [{"inventory_ref": "w-main", "attuned": True}]
    effects = resolve_active_effects(core, _inv_blade(), [], item_states, access)
    attacks = derive_attacks(core, _inv_blade(), {"strength": 2, "dexterity": 3},
                             item_states, effects, access)
    # Blade Alpha: 1d8 + Str(2), then the item's own +1d6 rider folds in
    assert attacks[0]["damage"] == "1d8+2+1d6"


def test_item_rider_absent_when_not_attuned(access):
    core = _blade_core()
    effects = resolve_active_effects(core, _inv_blade(), [], [], access)  # not attuned
    attacks = derive_attacks(core, _inv_blade(), {"strength": 2, "dexterity": 3},
                             [], effects, access)
    assert attacks[0]["damage"] == "1d8+2"   # requires attunement → rider does not fold


def test_item_rider_only_on_owning_weapon(access):
    """The rider folds into Blade Alpha's own attack only, never the other equipped weapon's."""
    core = _blade_core()
    inv = {"equipped": {"main_hand": {"id": "w-main", "name": "Blade Alpha"},
                        "off_hand": {"id": "w-off", "name": "Weapon A"}}}
    item_states = [{"inventory_ref": "w-main", "attuned": True}]
    effects = resolve_active_effects(core, inv, [], item_states, access)
    attacks = derive_attacks(core, inv, {"strength": 2, "dexterity": 3},
                             item_states, effects, access)
    by_name = {a["name"]: a["damage"] for a in attacks}
    assert by_name["Blade Alpha"] == "1d8+2+1d6"
    assert by_name["Weapon A"] == "1d12+2"   # rider does NOT leak to the other weapon


# ── effect-granted natural-weapon attack (T128) ───────────────────────────────


def _natwep_state():
    """An active self-buff state whose source spell (Spell Natwep) owns a grant_attack row."""
    return {"state": "altered", "source": "Spell Natwep", "source_type": "spell",
            "detail": {"option": "natural_weapons"}}


def test_granted_attack_accumulates(access):
    core = _core()
    effects = resolve_active_effects(core, None, [_natwep_state()], [], access)
    assert len(effects.attack_grants) == 1
    g = effects.attack_grants[0]
    assert g["owner_kind"] == "spell" and g["owner_id"] == "sp-natwep"
    assert g["ability_mode"] == "spellcasting"


def test_granted_natural_weapon_attack_derived(access):
    """The granted attack uses the character's spellcasting-ability modifier (class-a casts with a1,
    keyed x1 here → mod 3) for BOTH attack and damage, plus PB (2) on the attack (reshaped unarmed
    strike). Die term + damage type come from the DB row."""
    core = _core()  # proficiency_bonus 2
    effects = resolve_active_effects(core, None, [_natwep_state()], [], access)
    attacks = derive_attacks(core, None, {"x1": 3}, [], effects, access)
    granted = [a for a in attacks if a["name"] == "Attack Alpha"]
    assert len(granted) == 1
    a = granted[0]
    assert a["attack_bonus"] == 3 + 2      # spellcasting mod (3) + PB (2)
    assert a["damage"] == "1d6+3"          # 1d6 + spellcasting mod
    assert a["damage_type"] == "poison"    # carried straight from the grant row
    assert a["weapon_mastery"] is None


def test_no_granted_attack_without_state(access):
    core = _core()
    effects = resolve_active_effects(core, None, [], [], access)
    assert effects.attack_grants == []
    attacks = derive_attacks(core, None, {"x1": 3}, [], effects, access)
    assert [a for a in attacks if a["name"] == "Attack Alpha"] == []


# ── non-spellcasting ability_mode resolution (T136) ──────────────────────────


def _strmode_state():
    """An active self-buff granting a strength-mode attack (uses the Strength modifier)."""
    return {"state": "buffed", "source": "Spell Str Mode", "source_type": "spell", "detail": {}}


def _finmode_state():
    """An active self-buff granting a finesse-mode attack (best of Strength/Dexterity)."""
    return {"state": "buffed", "source": "Spell Fin Mode", "source_type": "spell", "detail": {}}


def test_granted_strength_mode_attack_uses_strength(access):
    """A 'strength' ability_mode grant adds the Strength modifier to bonus and damage, plus PB."""
    core = _core()  # proficiency_bonus 2
    effects = resolve_active_effects(core, None, [_strmode_state()], [], access)
    attacks = derive_attacks(core, None, {"strength": 2, "dexterity": 4}, [], effects, access)
    granted = [a for a in attacks if a["name"] == "Attack Str"]
    assert len(granted) == 1
    a = granted[0]
    assert a["attack_bonus"] == 2 + 2     # STR mod (2) + PB (2) -- NOT the higher DEX
    assert a["damage"] == "1d8+2"
    assert a["damage_type"] == "poison"
    assert a["properties"] == ["light"]


def test_granted_finesse_mode_picks_dexterity_when_higher(access):
    """A 'finesse' ability_mode grant adds the better of Strength/Dexterity (here DEX 4 > STR 2)."""
    core = _core()
    effects = resolve_active_effects(core, None, [_finmode_state()], [], access)
    attacks = derive_attacks(core, None, {"strength": 2, "dexterity": 4}, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack Fin"][0]
    assert a["attack_bonus"] == 4 + 2     # max(STR 2, DEX 4) + PB
    assert a["damage"] == "1d4+4"
    assert a["damage_type"] == "fire"


def test_granted_finesse_mode_picks_strength_when_higher(access):
    """Finesse picks Strength when it beats Dexterity (proves it is the max, not always DEX)."""
    core = _core()
    effects = resolve_active_effects(core, None, [_finmode_state()], [], access)
    attacks = derive_attacks(core, None, {"strength": 5, "dexterity": 1}, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack Fin"][0]
    assert a["attack_bonus"] == 5 + 2     # max(STR 5, DEX 1) + PB
    assert a["damage"] == "1d4+5"


# ── permanent-owner granted attack (always-on, no state) ─────────────────────


def test_permanent_owner_granted_attack_materializes(access):
    """A permanent owner (a feat) owning a finesse grant_attack materialises WITHOUT any active state
    or item — the always-on owner path (mirrors the owner ability-set path)."""
    core = _core(feats=[{"name": "Feat Owner Atk", "source": "bg-a"}])
    effects = resolve_active_effects(core, None, [], [], access)
    grants = [g for g in effects.attack_grants if g["owner_id"] == "feat-owneratk"]
    assert len(grants) == 1 and grants[0]["owner_kind"] == "feat"
    attacks = derive_attacks(core, None, {"strength": 1, "dexterity": 3}, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack Owner"][0]
    assert a["attack_bonus"] == 3 + 2     # finesse max(STR 1, DEX 3) + PB
    assert a["damage"] == "1d6+3"
    assert a["damage_type"] == "poison"


def test_no_permanent_owner_attack_without_the_owner(access):
    """The default core (which does not carry the granting feat) gains no permanent-owner attack."""
    core = _core()
    effects = resolve_active_effects(core, None, [], [], access)
    assert [g for g in effects.attack_grants if g["owner_id"] == "feat-owneratk"] == []


# ── item-owned granted attack (T134) ─────────────────────────────────────────


def test_item_attuned_granted_attack_materializes(access):
    """An attuned magic item owning a strength-mode grant_attack materialises at MODIFIER."""
    core = _core()
    inventory = {"equipped": {"hands": {"id": "item-hands", "name": "Claws Alpha"}}}
    item_states = [{"inventory_ref": "item-hands", "attuned": True}]
    effects = resolve_active_effects(core, inventory, [], item_states, access)
    attacks = derive_attacks(core, inventory, {"strength": 3, "dexterity": 1},
                             item_states, effects, access)
    a = [x for x in attacks if x["name"] == "Attack Claws"][0]
    assert a["attack_bonus"] == 3 + 2     # STR mod (3) + PB
    assert a["damage"] == "1d8+3"
    assert a["damage_type"] == "poison"


def test_item_attunement_required_not_attuned_no_attack(access):
    """An attunement-required item that is NOT attuned confers no granted attack."""
    core = _core()
    inventory = {"equipped": {"hands": {"id": "item-hands", "name": "Claws Alpha"}}}
    effects = resolve_active_effects(core, inventory, [], [], access)
    attacks = derive_attacks(core, inventory, {"strength": 3, "dexterity": 1}, [], effects, access)
    assert [x for x in attacks if x["name"] == "Attack Claws"] == []


def test_item_passive_on_equip_granted_attack_materializes(access):
    """A passive-on-equip (no-attunement) item owning a finesse grant_attack materialises when
    equipped, without attunement."""
    core = _core()
    inventory = {"equipped": {"head": {"id": "item-head", "name": "Fangs Alpha"}}}
    effects = resolve_active_effects(core, inventory, [], [], access)
    attacks = derive_attacks(core, inventory, {"strength": 1, "dexterity": 4}, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack Fangs"][0]
    assert a["attack_bonus"] == 4 + 2     # finesse max(STR 1, DEX 4) + PB
    assert a["damage"] == "1d6+4"
    assert a["damage_type"] == "fire"


# ── multi-caster spellcasting-ability disambiguation (T135) ──────────────────


def _mc_core(classes):
    """A core with the given caster classes; abilities/PB from _core (proficiency_bonus 2)."""
    return _core(identity={"name": "T", "species": "Species A", "size": "medium",
                           "creature_type": "Type A", "classes": classes,
                           "total_level": sum(c["level"] for c in classes),
                           "background": "Background A"})


def _mc_state(source):
    return {"state": "buffed", "source": source, "source_type": "spell", "detail": {}}


# class-cast1 casts with a1, class-cast2 with a2; abilities dict gives a1→3, a2→5.
_C1 = {"class": "Class Cast1", "level": 3, "subclass": None}
_C2 = {"class": "Class Cast2", "level": 3, "subclass": None}
_MC_ABIL = {"a1": 3, "a2": 5}


def test_mc_spell_resolves_carrier_ability_carrier_first(access):
    """Spell on cast1's list only, cast1 listed first → resolves cast1's ability (a1)."""
    core = _mc_core([_C1, _C2])
    effects = resolve_active_effects(core, None, [_mc_state("Spell MC Atk1")], [], access)
    attacks = derive_attacks(core, None, _MC_ABIL, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack MC1"][0]
    assert a["attack_bonus"] == 3 + 2     # a1 mod (3) + PB
    assert a["damage"] == "1d6+3"


def test_mc_spell_resolves_carrier_ability_regardless_of_order(access):
    """Ordering independence: the NON-carrier (cast2) listed FIRST, the carrier (cast1) second — the
    granted attack still resolves cast1's ability (a1), proving it is not 'the first caster'."""
    core = _mc_core([_C2, _C1])
    effects = resolve_active_effects(core, None, [_mc_state("Spell MC Atk1")], [], access)
    attacks = derive_attacks(core, None, _MC_ABIL, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack MC1"][0]
    assert a["attack_bonus"] == 3 + 2     # still a1 (3), NOT a2 (5)
    assert a["damage"] == "1d6+3"


def test_mc_spell_on_other_class_resolves_that_class(access):
    """Spell on cast2's list only → resolves cast2's ability (a2)."""
    core = _mc_core([_C1, _C2])
    effects = resolve_active_effects(core, None, [_mc_state("Spell MC Atk2")], [], access)
    attacks = derive_attacks(core, None, _MC_ABIL, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack MC2"][0]
    assert a["attack_bonus"] == 5 + 2     # a2 mod (5) + PB
    assert a["damage"] == "1d6+5"


def test_mc_spell_off_all_lists_falls_back_to_first_caster(access):
    """Single caster, granting spell off every class list → the fallback keeps the first caster's
    ability (a1)."""
    core = _mc_core([_C1])
    effects = resolve_active_effects(core, None, [_natwep_state()], [], access)
    attacks = derive_attacks(core, None, _MC_ABIL, [], effects, access)
    a = [x for x in attacks if x["name"] == "Attack Alpha"][0]
    assert a["attack_bonus"] == 3 + 2     # fallback → a1 (3) + PB
    assert a["damage"] == "1d6+3"
    assert a["damage_type"] == "poison"


# ── stats-less magic weapon attack materialization (T56) ─────────────────────


def test_stats_less_magic_weapon_materializes_attack(access):
    """A magic weapon with no base weapon-stats row still materialises an attack from its
    unambiguous base weapon (F05-T56); the item's own +1d6 rider then folds into it."""
    core = _core()
    inv = {"equipped": {"main_hand": {"id": "w-relic", "name": "Relic Blade Alpha"}}}
    effects = resolve_active_effects(core, inv, [], [], access)
    attacks = derive_attacks(core, inv, {"strength": 2, "dexterity": 3}, [], effects, access)
    assert len(attacks) == 1
    a = attacks[0]
    assert a["name"] == "Relic Blade Alpha"      # the magic item's name, not the base weapon's
    assert a["attack_bonus"] == 4                # base weapon-a: martial 1d12, Str(2) + PB(2)
    assert a["damage"] == "1d12+2+1d6"           # base 1d12 + Str, then the item's ungated rider
    assert "two-handed" in a["properties"]       # base weapon's properties resolve too


def test_multi_base_magic_weapon_resolves_canonical_base(access):
    """A stats-less magic weapon whose template names several base weapons resolves a DETERMINISTIC
    canonical base (the lowest id among the bases with a real weapon-stats row) rather than skipping
    the attack (T121). 'Ambi Blade Alpha' has bases weapon-a (martial 1d12 two-handed) and weapon-b
    (simple 1d6); the canonical base is weapon-a."""
    core = _core()
    inv = {"equipped": {"main_hand": {"id": "w-ambi", "name": "Ambi Blade Alpha"}}}
    effects = resolve_active_effects(core, inv, [], [], access)
    attacks = derive_attacks(core, inv, {"strength": 2, "dexterity": 3}, [], effects, access)
    assert len(attacks) == 1
    a = attacks[0]
    assert a["attack_bonus"] == 4            # canonical base weapon-a: martial 1d12, Str(2) + PB(2)
    assert a["damage"] == "1d12+2"           # base 1d12 + Str; mi-ambi-blade owns no rider
    assert "two-handed" in a["properties"]   # the canonical base's properties resolve too


# ── multi-row item extra-damage disambiguation (T57) ─────────────────────────


def test_multi_row_item_folds_only_ungated_rider(access):
    """A magic weapon owning several extra_damage rows folds ONLY the single ungated row into its
    own attack; the condition-gated variant is state-scoped and never leaks in (F05-T57)."""
    core = _blade_core()
    inv = {"equipped": {"main_hand": {"id": "w-multi", "name": "Multi Blade Alpha"}}}
    effects = resolve_active_effects(core, inv, [], [], access)
    attacks = derive_attacks(core, inv, {"strength": 2, "dexterity": 3}, [], effects, access)
    # base 1d8 + Str(2), then only the ungated +1d6 base rider — NOT the gated +3d6.
    assert attacks[0]["damage"] == "1d8+2+1d6"


def test_multiple_ungated_rows_fold_nothing(access):
    """Two UNGATED extra_damage rows remain ambiguous — the deriver folds nothing (never sums)."""
    core = _blade_core()
    inv = {"equipped": {"main_hand": {"id": "w-twin", "name": "Twin Blade Alpha"}}}
    effects = resolve_active_effects(core, inv, [], [], access)
    attacks = derive_attacks(core, inv, {"strength": 2, "dexterity": 3}, [], effects, access)
    assert attacks[0]["damage"] == "1d8+2"   # no rider folded, and definitely not 1d6+2d6 summed


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
    # NULL target_id (all-saves bonus): applies to every save
    effects.bonuses.append({"target_kind": "saving_throw", "value": 1, "target_id": None,
                            "source_name": "src-spell-b"})
    saves = derive_saving_throws(core, abilities, 2, effects, access)
    assert saves["a1"]["modifier"] == 5  # 2 + PB(2) + 1 bonus


def test_derive_saving_throws_per_ability_bonus(access):
    """Key-mismatch regression: the CORE save keys and the mods dict use the short codes
    (abbreviations x1/x2), while the grant's target_id is the full DB id (a1) — exactly the
    id/abbrev split real data has. The per-ability bonus must still land on x1's save, i.e. the
    deriver normalises the short key to the full id before matching target_id. (Keying abilities
    by the id, as the old fixture did, gave false confidence: the synthetic key equalled the id.)"""
    core = _core(saving_throws={"x1": {"proficient": True}, "x2": {"proficient": False}})
    abilities = {"x1": 2, "x2": 3}          # mods keyed by the CORE short code (abbrev)
    effects = ActiveEffects()
    effects.bonuses.append({"target_kind": "saving_throw", "value": 2, "target_id": "a1",
                            "source_name": "Amulet Alpha"})   # grant target is the full DB id
    saves = derive_saving_throws(core, abilities, 2, effects, access)
    assert saves["x1"]["modifier"] == 6  # 2 + PB(2) proficient + 2 item (x1 normalises to a1)
    assert saves["x2"]["modifier"] == 3  # 3 + 0, the a1-targeted bonus must NOT leak to x2


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


def test_derive_initiative_short_keyed_abilities_uses_real_dex_mod(access):
    """Folded regression (same family as AC/attacks): initiative looked up the full 'dexterity' id
    against a short-keyed abilities dict and silently returned 0. A short-keyed dict must now yield
    the real Dex mod."""
    access = _access_with_dex_str(access)
    abilities = {"str": 2, "dex": 3}   # keyed by the abbreviations (CORE short codes)
    assert derive_initiative({}, abilities, 2, _empty_effects(), access) == 3  # NOT 0 (pre-fix bug)


# ── derive_hp_effects ────────────────────────────────────────────────────────


def test_derive_hp_effects_baseline(access):
    hp = derive_hp_effects(_core(), _empty_effects(), {}, access)
    assert hp["max_boost"] == 0
    assert hp["max_reduction"] == 0


# ── state-gated max-HP reduction (drain/curse) (T58) ─────────────────────────


def _drain_state(source="HP Drain Feature A"):
    return {"state": "drained", "source": source, "source_type": "feature"}


def test_state_gated_max_hp_reduction_materializes(access):
    """A state-gated NEGATIVE grant_hp lowers max HP: while the 'drained' state is active the drain
    folds into hit_points.max_reduction (F05-T58)."""
    core = _core()
    effects = resolve_active_effects(core, None, [_drain_state()], [], access)
    assert effects.hp_reduction == 6
    assert effects.hp_boost == 0
    hp = derive_hp_effects(core, effects, {}, access)
    assert hp["max_reduction"] == 6
    assert hp["max_boost"] == 0


def test_max_hp_reduction_absent_without_state(access):
    """No active drain state → no reduction (the drain half is inert until its state is active)."""
    core = _core()
    effects = resolve_active_effects(core, None, [], [], access)
    assert effects.hp_reduction == 0
    assert derive_hp_effects(core, effects, {}, access)["max_reduction"] == 0


def test_max_hp_reduction_gate_no_leak(access):
    """A reduction gated to a different state id must not fire for the 'drained' state."""
    core = _core()
    effects = resolve_active_effects(core, None, [_drain_state("HP Drain Feature B")], [], access)
    assert effects.hp_reduction == 0


def test_variable_drain_not_folded_into_reduction(access):
    """A VARIABLE (dice-based) state drain is a live-play amount (the damage rolled), NOT a fixed
    derived magnitude — the deriver must not fabricate a reduction from it (F05-T112)."""
    core = _core()
    var_state = {"state": "drained-var", "source": "HP Drain Feature C", "source_type": "feature"}
    effects = resolve_active_effects(core, None, [var_state], [], access)
    assert effects.hp_reduction == 0
    assert derive_hp_effects(core, effects, {}, access)["max_reduction"] == 0


# ── derive_resource_state ────────────────────────────────────────────────────


def test_derive_resource_state(access):
    core = _core()
    core["resource_budgets"] = {"rage": {"max": 3}}
    state = derive_resource_state(core, _empty_effects(), access)
    assert state["rage"]["max"] == 3


# ── derive_attacks ───────────────────────────────────────────────────────────


def test_derive_attacks_melee(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Weapon A"}}}
    abilities = {"strength": 2, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert len(attacks) == 1
    a = attacks[0]
    assert a["name"] == "Weapon A"
    assert a["attack_bonus"] == 4  # 2 Str + 2 PB
    assert "d12" in a["damage"]
    assert "two-handed" in a["properties"]


def test_derive_attacks_short_keyed_abilities_uses_real_str_mod(access):
    """Folded regression: derive_attacks looked up the full 'strength'/'dexterity' ids against a
    short-keyed abilities dict and silently used 0. A Str-based weapon must now pick up the real
    Str mod (in both attack bonus and damage) from a short-keyed dict."""
    access = _access_with_dex_str(access)
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Weapon A"}}}
    abilities = {"str": 2, "dex": 3}   # keyed by the abbreviations (CORE short codes)
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert len(attacks) == 1
    assert attacks[0]["attack_bonus"] == 4   # Str(2) + PB(2) -- NOT 2 (pre-fix bug dropped Str)
    assert attacks[0]["damage"] == "1d12+2"  # Str mod flows into damage too


def test_derive_attacks_finesse(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w2", "name": "Weapon C"}}}
    abilities = {"strength": 1, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert len(attacks) == 1
    # Weapon C has no finesse, so it's melee (Str)
    assert attacks[0]["attack_bonus"] == 3  # 1 Str + 2 PB


def test_derive_attacks_proficient_via_specific_weapon(access):
    """A weapon-e is a MARTIAL weapon; a sheet proficient only with 'simple weapons' + the specific
    'weapon-es' grant is still proficient with it, so PB applies (tier-only matching would miss it)."""
    core = _core(proficiencies={"armor": [], "weapons": ["simple weapons", "weapon-es"], "tools": []})
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "weapon-e"}}}
    abilities = {"strength": 1, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert attacks[0]["attack_bonus"] == 5  # finesse -> Dex(3) + PB(2)


def test_derive_attacks_specific_weapon_singular(access):
    """The specific-weapon grant may appear singular ('weapon-e'); it must still match the weapon."""
    core = _core(proficiencies={"armor": [], "weapons": ["simple weapons", "weapon-e"], "tools": []})
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "weapon-e"}}}
    abilities = {"strength": 1, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert attacks[0]["attack_bonus"] == 5  # finesse -> Dex(3) + PB(2)


def test_derive_attacks_not_proficient_no_pb(access):
    """Neither the martial tier nor a specific grant matches the weapon-e -> no proficiency bonus."""
    core = _core(proficiencies={"armor": [], "weapons": ["simple weapons"], "tools": []})
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "weapon-e"}}}
    abilities = {"strength": 1, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert attacks[0]["attack_bonus"] == 3  # finesse -> Dex(3), NO PB


def test_derive_attacks_tier_title_case(access):
    """Robustness: a TITLE-CASE tier token ('Martial Weapons', as the generator emits from the
    catalog) still confers PB -- the tier match is case-insensitive. The lowercase corpus form is
    covered by the other attack tests."""
    core = _core(proficiencies={"armor": [], "weapons": ["Simple Weapons", "Martial Weapons"],
                                "tools": []})
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Weapon A"}}}
    abilities = {"strength": 2, "dexterity": 3}
    attacks = derive_attacks(core, inventory, abilities, [], _empty_effects(), access)
    assert attacks[0]["attack_bonus"] == 4  # 2 Str + 2 PB (Weapon A is martial)


def test_derive_attacks_bonus(access):
    core = _core()
    inventory = {"equipped": {"main_hand": {"id": "w1", "name": "Weapon A"}}}
    abilities = {"strength": 2}
    effects = ActiveEffects()
    effects.bonuses.append({"target_kind": "weapon_attack", "value": 1,
                            "source_name": "src-spell-c"})
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


# ── item-sourced senses / speeds (attuned + passive-on-equip) ────────────────


def test_item_attuned_sense_and_speed(access):
    core = _core()
    inventory = {"equipped": {"feet": {"id": "item-feet", "name": "Boots Alpha"}}}
    item_states = [{"inventory_ref": "item-feet", "attuned": True}]
    effects = resolve_active_effects(core, inventory, [], item_states, access)
    senses = derive_senses(core, effects, access)
    speeds, _ = derive_speed(core, effects, access)
    assert senses.get("darkvision") == 60   # item darkvision (== core, max keeps 60)
    assert speeds.get("fly") == 30           # item fly materialises at MODIFIER


def test_item_attunement_gated_when_not_attuned(access):
    core = _core()
    inventory = {"equipped": {"feet": {"id": "item-feet", "name": "Boots Alpha"}}}
    effects = resolve_active_effects(core, inventory, [], [], access)  # not attuned
    speeds, _ = derive_speed(core, effects, access)
    assert "fly" not in speeds   # attunement-gated item confers nothing unattuned


def test_item_passive_on_equip_sense(access):
    core = _core()
    inventory = {"equipped": {"head": {"id": "item-head", "name": "Goggles Alpha"}}}
    effects = resolve_active_effects(core, inventory, [], [], access)  # no attunement
    senses = derive_senses(core, effects, access)
    assert senses.get("blindsight") == 10   # passive-on-equip, no attunement needed


def test_item_equipped_and_spuriously_attuned_counts_once(access):
    """A non-attunement item that is both equipped AND (spuriously) flagged attuned
    must contribute its additive speed once, not once per branch (attuned branch +
    passive-on-equip branch)."""
    core = _core()
    inventory = {"equipped": {"feet": {"id": "item-ankle", "name": "Anklet Alpha"}}}
    item_states = [{"inventory_ref": "item-ankle", "attuned": True}]
    effects = resolve_active_effects(core, inventory, [], item_states, access)
    speeds, _ = derive_speed(core, effects, access)
    assert speeds.get("walk") == 40   # base 30 + one +10 additive (not +20)


# ── T78: validator-independence of the senses/speed resolution ───────────────


def test_deriver_does_not_import_validator_senses_or_speed_resolver():
    """The MODIFIER deriver must NOT import the validator's rule-bearing senses/speed resolvers
    (nor their grant-gather walkers). If it did, the validator's movement/senses checks would agree
    with the deriver by construction and give zero independent coverage of those fields (F05-T78)."""
    import ast
    import inspect
    from app.derivation import modifier as modmod

    tree = ast.parse(inspect.getsource(modmod))
    banned_modules = {"validator.checks.movement", "validator.checks.senses"}
    # The validator's rule-bearing resolvers — importing either would make the movement/senses checks
    # agree with the deriver by construction (F05-T78/T96). The grant-gather walkers are legitimately
    # shared access helpers post-T96, so they are NOT banned; the resolver names are what must stay out.
    banned_names = {"_resolve_speeds", "_resolve_senses"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in banned_modules, (
                f"deriver imports from {node.module} — breaks T78 independence")
            for alias in node.names:
                assert alias.name not in banned_names, (
                    f"deriver imports {alias.name!r} — breaks T78 independence")


def test_validator_movement_and_senses_do_not_import_deriver():
    """Independence is severed in BOTH directions (F05-T78): the validator's movement and senses
    checks must not import from the deriver either. Each side reads the DB on its own."""
    import ast
    import inspect
    from validator.checks import movement as mv
    from validator.checks import senses as se

    for module in (mv, se):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules.extend(a.name for a in node.names)
            for m in modules:
                assert not m.startswith("app.derivation"), (
                    f"{module.__name__} imports {m} from the deriver — breaks T78 independence")


def test_deriver_and_validator_resolve_multimode_speed_identically_from_db(access):
    """Behavioural independence: the deriver's OWN speed resolver and the validator's resolve the
    same multi-mode owner identically — read purely from the DB, not by sharing code. This is the
    climb+swim walk-equal case T52 flagged as the byte-order hazard. ``sub-a`` already grants
    swim==walk; a climb==walk grant is added so one owner exercises TWO walk-equal modes."""
    import sqlite3

    from access.validator import ValidatorAccess
    from access.validator import movement as movement_q
    from validator.checks.movement import _resolve_speeds as validator_resolve
    from app.derivation import modifier as modmod

    con = sqlite3.connect(access.db.path)
    con.execute("INSERT INTO grant_speed VALUES "
                "('gsd-sub-climb','subclass','sub-a',3,'climb',NULL,1,0,0,NULL,NULL)")
    con.commit()
    con.close()
    acc = ValidatorAccess(path=access.db.path)

    rows = movement_q.speed_grants(acc, "subclass", "sub-a", 3)
    base_walk = 30

    deriver = modmod._resolve_speeds(rows, base_walk, [])
    validator = validator_resolve(rows, base_walk, [])

    assert deriver == validator == {"walk": 30, "climb": 30, "swim": 30}
    # sorted() key order — byte-reproducible across hash seeds (T52).
    assert list(deriver.keys()) == ["walk", "climb", "swim"]


def test_deriver_speed_resolver_zero_modes_dropped():
    """The deriver-owned resolver drops any zero-valued mode, so a baseless build never emits a
    spurious ``walk 0`` — matching the validator's resolver and the CORE deriver (T67)."""
    from app.derivation import modifier as modmod
    assert modmod._resolve_speeds([], 0, []) == {}
    assert modmod._resolve_speeds([], 30, []) == {"walk": 30}


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
    hp = derive_hp_effects(core, effects, mods, access)
    res = derive_resource_state(core, effects, access)
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
