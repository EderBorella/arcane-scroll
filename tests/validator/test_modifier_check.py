"""Tests for the MODIFIER validator."""
from validator.checks.modifier import check
from validator.checks import ALL_CHECKS


def _sheet(**overrides):
    s = {
        "core": {
            "identity": {"size": "medium"},
            "abilities": {
                "a1": {"final": 14},
                "a2": {"final": 16},
                "a3": {"final": 12},
            },
            "proficiency_bonus": 2,
            "saving_throws": {
                "a1": {"proficient": True},
                "a2": {"proficient": False},
                "a3": {"proficient": True},
            },
            "skills": {
                "sk1": {"ability": "a1", "proficient": True, "expertise": False},
                "sk2": {"ability": "a2", "proficient": False, "expertise": False},
            },
            "permanent_defenses": {
                "resistances": ["fire"], "immunities": [], "vulnerabilities": [],
                "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
            },
            "features": [{"name": "Feat A"}],
            "feats": [{"name": "feat-gen"}],
        },
        "inventory": {},
        "grimoire": {"spells": [
            {"name": "Sp3", "source": "class:class-a", "bucket": "prepared"},
        ]},
        "modifier": {
            "schema_version": 1,
            "character_id": "test", "character_name": "Test",
            "xp": 0, "treasure": {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0},
            "hit_points": {"current": 22, "temp": 0, "max_boost": 0, "max_reduction": 0},
            "death_saves": {"successes": 0, "failures": 0},
            "hit_dice": {"d8": {"remaining": 3}},
            "spell_slots": {"1": {"remaining": 4}, "2": {"remaining": 2}},
            "pact_slots": {"1": {"remaining": 0}},
            "resource_state": {"x": {"max": 1, "remaining": 1, "recharge": None, "recharge_amount": None}},
            "abilities": {
                "a1": {"modifier": 2, "reduction": 0},
                "a2": {"modifier": 3, "reduction": 0},
                "a3": {"modifier": 1, "reduction": 0},
                # Dexterity contribution for the unarmoured-defence AC re-derivation (the base
                # default is 10 + Dexterity → 13). Keyed by the canonical id the AC math resolves.
                "dexterity": {"modifier": 3, "reduction": 0},
            },
            "saving_throws": {
                "a1": {"modifier": 4},
                "a2": {"modifier": 3},
                "a3": {"modifier": 3},
            },
            "skills": {
                "sk1": {"modifier": 4},
                "sk2": {"modifier": 3},
            },
            "passive_scores": {"sk1": 14, "sk2": 13},
            "effective_senses": {"sense-a": 60},
            "effective_defenses": {
                "resistances": ["fire"], "immunities": [], "vulnerabilities": [],
                "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
            },
            "effective_size": "medium",
            "effective_abilities": {"a1": 14, "a2": 16, "a3": 12},
            "armor_class": 13,
            "armor_class_detail": {
                "source": "unarmored", "base": 10, "dex_bonus": 3,
                "bonuses": [], "floor": None,
            },
            "initiative": 3,
            "speed": {"walk": 30},
            "speed_detail": {"base": 30, "base_source": "species", "base_mode": "walk", "modifiers": []},
            "attacks": [],
            "character_states": [],
            "item_states": [],
            "features": [{"name": "Feat A", "uses": {"max": None}}],
            "feats": [{"name": "feat-gen", "uses": {"max": None}}],
            "prepared_spells": [],
        },
    }
    s.update(overrides)
    return s


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ── valid sheet ──────────────────────────────────────────────────────────────


def test_valid_sheet_passes(access):
    assert check(_sheet(), access) == []


# ── AC checks ────────────────────────────────────────────────────────────────


def test_ac_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class"] = 99
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_bonus_duplicate_source(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class_detail"]["bonuses"] = [
        {"value": 2, "source": "spell-ac-1"},
        {"value": 1, "source": "spell-ac-1"},
    ]
    sheet["modifier"]["armor_class"] = 10 + 3 + 2 + 1
    assert "ac-bonus-duplicate-source" in _codes(sheet, access)


def test_ac_bonus_different_source_ok(access):
    sheet = _sheet()
    sheet["modifier"]["armor_class_detail"]["bonuses"] = [
        {"value": 2, "source": "spell-ac-1"},
        {"value": 1, "source": "spell-ac-2"},
    ]
    sheet["modifier"]["armor_class"] = 10 + 3 + 2 + 1
    assert "ac-bonus-duplicate-source" not in _codes(sheet, access)


# ── unarmoured-defence AC formulas, re-derived independently (F05-T140) ────────


def _ac_sheet(classes, dex=3, a3=1, equipped=None, item_states=None):
    """A MODIFIER sheet exercising the unarmoured-defence AC re-derivation. Dexterity + a3 are the
    two abilities the synthetic formulas sum; the caller sets armor_class per-test."""
    sheet = _sheet()
    sheet["core"]["identity"]["classes"] = classes
    sheet["modifier"]["abilities"]["dexterity"] = {"modifier": dex, "reduction": 0}
    sheet["modifier"]["abilities"]["a3"] = {"modifier": a3, "reduction": 0}
    if equipped is not None:
        sheet["inventory"] = {"equipped": equipped}
    if item_states is not None:
        sheet["modifier"]["item_states"] = item_states
    return sheet


def test_ac_formula_dex_plus_second_ability_correct(access):
    """class-b sums Dexterity + a3: 10 + 3 + 1 = 14 (not the base default's 13)."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}])
    sheet["modifier"]["armor_class"] = 14
    assert "ac-mismatch" not in _codes(sheet, access)


def test_ac_formula_wrong_base_flagged(access):
    """Authoring the base-default AC (13) for a build that qualifies for the higher formula (14) is
    caught — the re-derivation reads the formula from the DB, not the sheet's own base."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}])
    sheet["modifier"]["armor_class"] = 13
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_formula_ignores_shield_when_not_allowed(access):
    """A no-shield formula (class-b) does not add an equipped shield: 10 + 3 + 4 = 17, not 19."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}], a3=4,
                      equipped={"shield": {"id": "s1", "name": "Shield"}})
    sheet["modifier"]["armor_class"] = 17
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 19
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_formula_adds_shield_when_allowed(access):
    """A shield-permitting formula (subclass sub-a at level 3) adds the shield: 10+3+1+2 = 16."""
    sheet = _ac_sheet([{"class": "Class A", "level": 3, "subclass": "Sub A"}],
                      equipped={"shield": {"id": "s1", "name": "Shield"}})
    sheet["modifier"]["armor_class"] = 16
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 14  # shield wrongly excluded
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_formula_picks_most_beneficial(access):
    """Several applicable formulas → the highest wins (subclass sub-a's 14 over class-a's 13)."""
    sheet = _ac_sheet([{"class": "Class A", "level": 3, "subclass": "Sub A"}])
    sheet["modifier"]["armor_class"] = 14
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 13
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_formula_level_gated(access):
    """A subclass formula gained at level 3 does not apply at level 2 → base default 13."""
    sheet = _ac_sheet([{"class": "Class A", "level": 2, "subclass": "Sub A"}])
    sheet["modifier"]["armor_class"] = 13
    assert "ac-mismatch" not in _codes(sheet, access)


def test_ac_worn_armor_overrides_formula(access):
    """Worn body armour overrides a higher formula: class-b would give 17, but heavy Armor A
    (base 16, Dex cap 0) yields 16."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}], a3=4,
                      equipped={"armor": {"id": "a1", "name": "Armor A"}})
    sheet["modifier"]["armor_class"] = 16
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 17  # the (overridden) formula value
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_bonus_stacks_on_formula(access):
    """An attuned item's +1 AC (a protection-ring analogue) stacks on the chosen formula:
    class-b 14 + 1 = 15."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}],
                      equipped={"finger": {"id": "item-finger", "name": "Ring Beta"}},
                      item_states=[{"inventory_ref": "item-finger", "attuned": True}])
    sheet["modifier"]["armor_class"] = 15
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 14  # the magic bonus dropped
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_no_formula_class_falls_back_to_base(access):
    """A class with no AC formula falls back to 10 + Dexterity; the second ability must not leak in."""
    sheet = _ac_sheet([{"class": "Class Cast1", "level": 3, "subclass": None}], dex=3, a3=5)
    sheet["modifier"]["armor_class"] = 13
    assert "ac-mismatch" not in _codes(sheet, access)


def test_ac_validator_independent_of_detail_rubber_stamp(access):
    """The re-derivation NEVER trusts armor_class_detail: a sheet whose detail 'agrees' with a wrong
    armor_class (base 10 + dex 3 = 13) is still flagged, because the DB formula (class-b, 17) is the
    real expectation. Proves the old rubber-stamp (compute-from-detail) is gone."""
    sheet = _ac_sheet([{"class": "Class B", "level": 1, "subclass": None}], a3=4)
    sheet["modifier"]["armor_class"] = 13
    sheet["modifier"]["armor_class_detail"] = {
        "source": "unarmored", "base": 10, "dex_bonus": 3, "bonuses": [], "floor": None,
    }
    assert "ac-mismatch" in _codes(sheet, access)


# ── magic armour / shield as base + enchantment overlay (F05-T145) ────────────


def test_ac_magic_armor_single_base(access):
    """A magic body armour with no armor row re-derives its base from the single template base (heavy
    'armor-d', base 16, Dex cap 0) plus its own +1 ac enchantment: 17."""
    sheet = _ac_sheet([], equipped={"armor": {"id": "a1", "name": "Armor Alpha"}})
    sheet["modifier"]["armor_class"] = 17
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 16  # enchantment dropped
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_armor_sheet_chosen_base(access):
    """A generic magic armour (no template base) re-derives its base from the sheet's ``base_item``
    (light 'armor-e', base 11) plus its own +2 ac: 11 + Dex(3) + 2 = 16."""
    sheet = _ac_sheet([], equipped={
        "armor": {"id": "a1", "name": "Armor Gamma", "base_item": "armor-e"}})
    sheet["modifier"]["armor_class"] = 16
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 14  # wrong base / missing enchantment
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_shield(access):
    """A magic shield with no armor row re-derives its base +2 plus its own +1 ac enchantment on the
    shield-permitting base formula: 10 + Dex(3) + 3 = 16."""
    sheet = _ac_sheet([], equipped={"shield": {"id": "s1", "name": "Shield Alpha"}})
    sheet["modifier"]["armor_class"] = 16
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 13  # shield base + enchantment dropped
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_armor_and_shield_combined(access):
    """Worn magic armour + magic shield: 16 + 0 Dex + shield(2+1) + armour(1) = 20."""
    sheet = _ac_sheet([], equipped={
        "armor": {"id": "a1", "name": "Armor Alpha"},
        "shield": {"id": "s1", "name": "Shield Alpha"},
    })
    sheet["modifier"]["armor_class"] = 20
    assert "ac-mismatch" not in _codes(sheet, access)


def test_ac_worn_magic_armor_attuned_not_double_counted(access):
    """A worn magic armour credited in the base path is EXCLUDED from the magic-bonus channel, so an
    attuned worn armour is not double-counted: it stays 17, not 18."""
    sheet = _ac_sheet([], equipped={"armor": {"id": "a1", "name": "Armor Alpha"}},
                      item_states=[{"inventory_ref": "a1", "attuned": True}])
    sheet["modifier"]["armor_class"] = 17
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 18  # the double-counted value
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_armor_unresolved_base_falls_through(access):
    """A generic magic armour with no template base and no sheet ``base_item`` cannot resolve a base:
    the expected AC falls through to Unarmoured Defence, and its enchantment is dropped too."""
    sheet = _ac_sheet([], equipped={"armor": {"id": "a1", "name": "Armor Gamma"}})
    sheet["modifier"]["armor_class"] = 13
    assert "ac-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["armor_class"] = 15  # enchantment wrongly applied to a guessed base
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_magic_armor_independent_of_detail(access):
    """The re-derivation never trusts armor_class_detail: a detail that 'agrees' with a wrong AC (16)
    is still flagged, because the DB re-derivation expects 17 (base 16 + enchantment 1)."""
    sheet = _ac_sheet([], equipped={"armor": {"id": "a1", "name": "Armor Alpha"}})
    sheet["modifier"]["armor_class"] = 16
    sheet["modifier"]["armor_class_detail"] = {
        "source": "mi-armor", "base": 16, "dex_bonus": 0, "bonuses": [], "floor": None,
    }
    assert "ac-mismatch" in _codes(sheet, access)


def test_ac_deriver_validator_agree_magic_armor_and_shield(access):
    """The deriver's own AC output passes the INDEPENDENT validator re-derivation for worn magic
    armour + magic shield with the armour attuned — the two layers agree without sharing code."""
    from engine.derivation.modifier import derive_ac, resolve_active_effects
    sheet = _ac_sheet([], equipped={
        "armor": {"id": "a1", "name": "Armor Alpha"},
        "shield": {"id": "s1", "name": "Shield Alpha"},
    }, item_states=[{"inventory_ref": "a1", "attuned": True}])
    core, inventory = sheet["core"], sheet["inventory"]
    effects = resolve_active_effects(
        core, inventory, [], sheet["modifier"]["item_states"], access)
    ac, _ = derive_ac(core, inventory, effects, {"dexterity": 3}, access)
    sheet["modifier"]["armor_class"] = ac
    assert "ac-mismatch" not in _codes(sheet, access)


# ── saving throws ────────────────────────────────────────────────────────────


def test_save_modifier_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["saving_throws"]["a1"]["modifier"] = 99
    assert "save-modifier-mismatch" in _codes(sheet, access)


def test_save_item_bonus_stacks(access):
    """Two attuned all-saves items stack (+1 each = +2) into the expected save."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {
        "finger_1": {"id": "item-finger_1", "name": "Ring Alpha"},
        "back": {"id": "item-back", "name": "Cloak Alpha"},
    }}
    sheet["modifier"]["item_states"] = [
        {"inventory_ref": "item-finger_1", "attuned": True},
        {"inventory_ref": "item-back", "attuned": True},
    ]
    sheet["modifier"]["saving_throws"]["a1"]["modifier"] = 4 + 2
    sheet["modifier"]["saving_throws"]["a2"]["modifier"] = 3 + 2
    sheet["modifier"]["saving_throws"]["a3"]["modifier"] = 3 + 2
    assert "save-modifier-mismatch" not in _codes(sheet, access)


def test_save_item_bonus_missing_flagged(access):
    """An attuned save-bonus item that is not reflected in the save is a mismatch."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {
        "finger_1": {"id": "item-finger_1", "name": "Ring Alpha"},
    }}
    sheet["modifier"]["item_states"] = [
        {"inventory_ref": "item-finger_1", "attuned": True},
    ]
    # saves left unchanged despite the +1 item bonus -> mismatch
    assert "save-modifier-mismatch" in _codes(sheet, access)


def test_save_item_bonus_per_ability(access):
    """A per-ability (target_id set) item save bonus applies to that ability only."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {
        "neck": {"id": "item-neck", "name": "Amulet Alpha"},
    }}
    sheet["modifier"]["item_states"] = [
        {"inventory_ref": "item-neck", "attuned": True},
    ]
    sheet["modifier"]["saving_throws"]["a1"]["modifier"] = 4 + 2  # +2 on a1 only
    # a2 (3) and a3 (3) unchanged — the bonus does NOT apply to them
    assert "save-modifier-mismatch" not in _codes(sheet, access)


def test_save_item_bonus_per_ability_wrong_target(access):
    """The per-ability bonus applied to the wrong save is flagged."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {
        "neck": {"id": "item-neck", "name": "Amulet Alpha"},
    }}
    sheet["modifier"]["item_states"] = [
        {"inventory_ref": "item-neck", "attuned": True},
    ]
    sheet["modifier"]["saving_throws"]["a1"]["modifier"] = 4 + 2  # a1 correct
    sheet["modifier"]["saving_throws"]["a2"]["modifier"] = 3 + 2  # bonus wrongly on a2
    assert "save-modifier-mismatch" in _codes(sheet, access)


def _rekey_saves_short(sheet):
    """Re-key the sheet's CORE + MODIFIER saves and abilities by the short code (abbrev x1/x2/x3),
    mirroring the id/abbrev split of real sheets (CORE keys by short code; grant target ids are
    full ids)."""
    sheet["core"]["saving_throws"] = {"x1": {"proficient": True}, "x2": {"proficient": False},
                                      "x3": {"proficient": True}}
    sheet["core"]["abilities"] = {"x1": {"final": 14}, "x2": {"final": 16}, "x3": {"final": 12}}
    sheet["modifier"]["abilities"] = {"x1": {"modifier": 2, "reduction": 0},
                                      "x2": {"modifier": 3, "reduction": 0},
                                      "x3": {"modifier": 1, "reduction": 0}}
    sheet["modifier"]["saving_throws"] = {"x1": {"modifier": 4}, "x2": {"modifier": 3},
                                          "x3": {"modifier": 3}}
    sheet["inventory"] = {"equipped": {"neck": {"id": "item-neck", "name": "Amulet Alpha"}}}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-neck", "attuned": True}]
    return sheet


def test_save_item_bonus_per_ability_short_keyed(access):
    """Key-mismatch regression: the MODIFIER/CORE saves are keyed by the short code (abbrev x1),
    while the amulet's per-ability save bonus is keyed by the grant target_id (the full id a1). The
    +2 must still land on x1's save — the check normalises the short key to the full id before
    matching. (Keying by the id, as the sibling test does, hid this: the synthetic key equalled the
    id.)"""
    sheet = _rekey_saves_short(_sheet())
    sheet["modifier"]["saving_throws"]["x1"]["modifier"] = 4 + 2   # x1 (== a1) gets the +2
    # x2/x3 unchanged: the a1-targeted bonus must NOT leak to them
    assert "save-modifier-mismatch" not in _codes(sheet, access)


def test_save_item_bonus_per_ability_short_keyed_wrong_target(access):
    """Same short-keyed sheet: applying the a1-targeted +2 to x2 (not x1) is flagged."""
    sheet = _rekey_saves_short(_sheet())
    sheet["modifier"]["saving_throws"]["x1"]["modifier"] = 4 + 2   # x1 correct
    sheet["modifier"]["saving_throws"]["x2"]["modifier"] = 3 + 2   # x2 WRONG (bonus must not apply)
    assert "save-modifier-mismatch" in _codes(sheet, access)


def test_deriver_validator_agree_per_ability_save(access):
    """End-to-end: derive the MODIFIER with a per-ability item save bonus, then
    validate it. Deriver and validator must agree (no save-modifier-mismatch), and
    the bonus must land on the targeted ability only."""
    from engine.derivation.modifier_orchestrator import derive_modifier
    core = {
        "character_id": "t", "character_name": "T",
        # Species Slotless carries no ability-set grant, so a2 is not overridden — this test is
        # about a per-ability ITEM save bonus, not an always-on ability set (species-a would SET a2).
        "identity": {"size": "medium", "species": "Species Slotless", "lineage": None,
                     "classes": [{"class": "Class A", "level": 3, "subclass": None}]},
        "abilities": {"a1": {"final": 14}, "a2": {"final": 16}, "a3": {"final": 12}},
        "proficiency_bonus": 2,
        "saving_throws": {"a1": {"proficient": True}, "a2": {"proficient": False},
                          "a3": {"proficient": True}},
        "skills": {}, "features": [], "feats": [],
        "hit_points": {"max": 22}, "hit_dice": {},
    }
    inventory = {"equipped": {"neck": {"id": "item-neck", "name": "Amulet Alpha"}}}
    existing = {"item_states": [{"inventory_ref": "item-neck", "attuned": True}]}
    modifier, _ = derive_modifier(core, inventory, None, existing, "fill", access)
    sheet = {"core": core, "inventory": inventory, "grimoire": {}, "modifier": modifier}
    assert "save-modifier-mismatch" not in _codes(sheet, access)
    assert modifier["saving_throws"]["a1"]["modifier"] == 6   # 2 + PB(2) + 2 item (a1)
    assert modifier["saving_throws"]["a2"]["modifier"] == 3   # no per-ability bonus


# ── skills ───────────────────────────────────────────────────────────────────


def test_skill_modifier_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["skills"]["sk1"]["modifier"] = 99
    assert "skill-modifier-mismatch" in _codes(sheet, access)


# ── attacks ──────────────────────────────────────────────────────────────────


def _attack_sheet(weapons, weapon_name, str_mod=1, dex_mod=3):
    """A sheet wielding one weapon in main_hand, with str/dex mods keyed by their full DB ids so the
    attack check resolves them directly. `weapons` is the CORE proficiencies.weapons list."""
    sheet = _sheet()
    sheet["core"]["proficiencies"] = {"armor": [], "weapons": weapons, "tools": []}
    sheet["inventory"] = {"equipped": {"main_hand": {"id": "w-main", "name": weapon_name}}}
    sheet["modifier"]["abilities"]["strength"] = {"modifier": str_mod, "reduction": 0}
    sheet["modifier"]["abilities"]["dexterity"] = {"modifier": dex_mod, "reduction": 0}
    return sheet


def test_attack_proficient_via_tier(access):
    """Weapon E is martial; proficiency via the 'martial weapons' tier adds PB. Finesse -> Dex."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # str 1, dex 3
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2}]  # Dex(3) + PB(2)
    assert "attack-bonus-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3}]  # missing PB
    assert "attack-bonus-mismatch" in _codes(sheet, access)


def test_attack_proficient_via_specific_weapon(access):
    """Proficient only via the specific 'weapon-es' grant (not the martial tier) -> PB still applies."""
    sheet = _attack_sheet(["simple weapons", "weapon-es"], "weapon-e")
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2}]  # Dex(3) + PB(2)
    assert "attack-bonus-mismatch" not in _codes(sheet, access)


def test_attack_not_proficient_no_pb(access):
    """No matching tier or specific grant -> no PB."""
    sheet = _attack_sheet(["simple weapons"], "weapon-e")  # weapon-e is martial, not covered
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3}]  # Dex(3), no PB
    assert "attack-bonus-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2}]  # PB wrongly added
    assert "attack-bonus-mismatch" in _codes(sheet, access)


def test_attack_finesse_uses_max_of_str_dex(access):
    """Finesse picks max(str, dex): here str(5) > dex(1), so Str is used."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e", str_mod=5, dex_mod=1)
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 5 + 2}]  # Str(5) + PB(2)
    assert "attack-bonus-mismatch" not in _codes(sheet, access)


def test_attack_item_weapon_attack_bonus(access):
    """An attuned item's +1 weapon_attack bonus lands on the attack."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # dex 3
    sheet["inventory"]["equipped"]["waist"] = {"id": "item-waist", "name": "Charm Alpha"}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-waist", "attuned": True}]
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2 + 1}]  # Dex+PB+item
    assert "attack-bonus-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2}]  # item bonus missing
    assert "attack-bonus-mismatch" in _codes(sheet, access)


def test_attack_tier_title_case(access):
    """Robustness: a TITLE-CASE tier token ('Martial Weapons') still confers PB -- the validator's
    tier match is case-insensitive (independent of the deriver's copy)."""
    sheet = _attack_sheet(["Simple Weapons", "Martial Weapons"], "weapon-e")  # dex 3
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2}]  # Dex(3) + PB(2)
    assert "attack-bonus-mismatch" not in _codes(sheet, access)


# ── real-weapon damage (F05-T139) ────────────────────────────────────────────
# weapon-e: 1d8, finesse (ability mod = max(str,dex)); dmg_flat NULL. _attack_sheet defaults
# str_mod=1, dex_mod=3 -> ability damage mod = 3, so the base with no item bonus is "1d8+3".


def test_real_weapon_damage_base_ok(access):
    """A real weapon's base damage (dice + finesse ability mod, no item bonus) validates correct."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # ab mod 3
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+3"}]
    assert "real-weapon-damage-mismatch" not in _codes(sheet, access)


def test_real_weapon_damage_item_bonus_ok(access):
    """An attuned item's +1 UNSCOPED weapon_damage folds into a real weapon's damage base (1d8+3 -> 1d8+4)."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # ab mod 3
    sheet["inventory"]["equipped"]["waist"] = {"id": "item-hilt", "name": "Hilt Alpha"}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-hilt", "attuned": True}]
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+4"}]
    assert "real-weapon-damage-mismatch" not in _codes(sheet, access)


def test_real_weapon_damage_item_bonus_missing_flagged(access):
    """With the item attuned the base must be 1d8+4; the unmodified 1d8+3 (bonus dropped) is flagged."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")
    sheet["inventory"]["equipped"]["waist"] = {"id": "item-hilt", "name": "Hilt Alpha"}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-hilt", "attuned": True}]
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+3"}]
    assert "real-weapon-damage-mismatch" in _codes(sheet, access)


def test_real_weapon_damage_leaked_bonus_flagged(access):
    """A weapon_damage bonus present on the sheet with no backing item (1d8+4, expected 1d8+3) is flagged."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # no item
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+4"}]
    assert "real-weapon-damage-mismatch" in _codes(sheet, access)


def test_real_weapon_damage_wrong_flat_total_flagged(access):
    """Base extraction distinguishes a wrong flat total from a rider: 1d8+30 != expected 1d8+3."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+30"}]
    assert "real-weapon-damage-mismatch" in _codes(sheet, access)


def test_real_weapon_damage_scoped_bonus_not_counted(access):
    """A weapon_damage bonus SCOPED to a granted attack (target_id set) must NOT fold onto a real
    weapon: Gauntlet Alpha's scoped +1 belongs to its granted attack, so weapon-e stays 1d8+3."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")  # ab mod 3
    sheet["inventory"]["equipped"]["hands"] = {"id": "item-gaunt", "name": "Gauntlet Alpha"}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-gaunt", "attuned": True}]
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+3"}]
    assert "real-weapon-damage-mismatch" not in _codes(sheet, access)
    # if the scoped +1 WERE wrongly folded onto the real weapon, 1d8+4 would be expected -> 1d8+4 flags
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+4"}]
    assert "real-weapon-damage-mismatch" in _codes(sheet, access)


def test_real_weapon_damage_ignores_rider_tail(access):
    """An appended extra-damage rider (owned by the rider check) does not false-positive the base
    check: base 1d8+3 is read from '1d8+3+1d6'."""
    sheet = _attack_sheet(["martial weapons"], "weapon-e")
    sheet["modifier"]["attacks"] = [{"name": "weapon-e", "attack_bonus": 3 + 2, "damage": "1d8+3+1d6"}]
    assert "real-weapon-damage-mismatch" not in _codes(sheet, access)


# ── effective abilities ──────────────────────────────────────────────────────


def test_effective_ability_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["effective_abilities"]["a1"] = 5  # != expected 14 (no item grant)
    assert "effective-ability-mismatch" in _codes(sheet, access)


def test_effective_ability_no_item_must_equal_final(access):
    """Exact check: with no ability-set item, an effective score ABOVE the base is now a mismatch
    (the old lenient floor accepted anything >= base)."""
    sheet = _sheet()
    sheet["modifier"]["effective_abilities"]["a1"] = 19  # no item grant -> expected 14 -> mismatch
    assert "effective-ability-mismatch" in _codes(sheet, access)


def test_effective_ability_set_item_ok(access):
    """An attuned item that SETS a1 to 19 makes effective 19 the exact expectation."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {"waist": {"id": "item-waist", "name": "Belt Alpha"}}}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-waist", "attuned": True}]
    sheet["modifier"]["effective_abilities"]["a1"] = 19  # == set value
    assert "effective-ability-mismatch" not in _codes(sheet, access)
    # any other value is now flagged (exact, not a floor)
    sheet["modifier"]["effective_abilities"]["a1"] = 20
    assert "effective-ability-mismatch" in _codes(sheet, access)


def test_effective_ability_set_override_below_base(access):
    """`set` is a true override: Band Alpha sets a1 to 12, below the base (14). Effective must be
    12 (override), and the max/floor value (14) must be flagged."""
    sheet = _sheet()
    sheet["inventory"] = {"equipped": {"waist": {"id": "item-waist", "name": "Band Alpha"}}}
    sheet["modifier"]["item_states"] = [{"inventory_ref": "item-waist", "attuned": True}]
    sheet["modifier"]["effective_abilities"]["a1"] = 12  # override value -> ok
    assert "effective-ability-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["effective_abilities"]["a1"] = 14  # the pre-fix max()/floor value -> flagged
    assert "effective-ability-mismatch" in _codes(sheet, access)


def test_effective_ability_species_grant_override(access):
    """Cross-owner symmetry: an always-on species-owned grant_ability_set (a NON-item owner) is
    re-derived too. species-a SETs a2 to 20, so effective a2 must be 20 for that species."""
    sheet = _sheet()
    sheet["core"]["identity"] = {"size": "medium", "species": "Species A"}
    sheet["modifier"]["effective_abilities"]["a2"] = 20  # set by the species grant
    assert "effective-ability-mismatch" not in _codes(sheet, access)
    sheet["modifier"]["effective_abilities"]["a2"] = 16  # base, ignoring the species set -> flagged
    assert "effective-ability-mismatch" in _codes(sheet, access)


# ── defenses ─────────────────────────────────────────────────────────────────


def test_defense_missing_core_resistance(access):
    sheet = _sheet()
    sheet["modifier"]["effective_defenses"]["resistances"] = []
    assert "defense-subset-violation" in _codes(sheet, access)


# ── passive scores ───────────────────────────────────────────────────────────


def test_passive_score_mismatch(access):
    sheet = _sheet()
    sheet["modifier"]["passive_scores"]["sk1"] = 99
    assert "passive-score-mismatch" in _codes(sheet, access)


# ── features & feats ─────────────────────────────────────────────────────────


def test_missing_feature(access):
    sheet = _sheet()
    sheet["modifier"]["features"] = []
    assert "feature-missing" in _codes(sheet, access)


def test_missing_feat(access):
    sheet = _sheet()
    sheet["modifier"]["feats"] = []
    assert "feat-missing" in _codes(sheet, access)


# ── prepared spells ──────────────────────────────────────────────────────────


def test_prepared_spells_empty_ok(access):
    sheet = _sheet()
    assert "prepared-spells-invalid" not in _codes(sheet, access)


def test_prepared_spells_invalid(access):
    sheet = _sheet()
    sheet["modifier"]["prepared_spells"] = ["nonexistent|class:nonexistent"]
    assert "prepared-spells-invalid" in _codes(sheet, access)


def test_prepared_spells_valid(access):
    sheet = _sheet()
    sheet["modifier"]["prepared_spells"] = ["Sp3|class:class-a"]
    assert "prepared-spells-invalid" not in _codes(sheet, access)


# ── state compatibility ──────────────────────────────────────────────────────


def test_state_incompatible(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [
        {"state": "raging", "source": "test-rage", "source_type": "feature"},
        {"state": "concentrating", "source": "test-spell", "source_type": "spell"},
    ]
    assert "state-incompatible" in _codes(sheet, access)


def test_state_compatible(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [
        {"state": "raging", "source": "test-rage", "source_type": "feature"},
        {"state": "inspired", "source": "test-inspiration", "source_type": "feature"},
    ]
    assert "state-incompatible" not in _codes(sheet, access)


# ── defense subset: save & condition advantages (T44b) ───────────────────────


def test_save_advantage_subset_missing(access):
    sheet = _sheet()
    sheet["core"]["permanent_defenses"]["save_advantages"] = ["Dex"]
    sheet["modifier"]["effective_defenses"]["save_advantages"] = []
    assert "defense-subset-violation" in _codes(sheet, access)


def test_save_advantage_subset_present_ok(access):
    sheet = _sheet()
    sheet["core"]["permanent_defenses"]["save_advantages"] = ["Dex"]
    sheet["modifier"]["effective_defenses"]["save_advantages"] = ["Dex"]
    assert "defense-subset-violation" not in _codes(sheet, access)


def test_condition_advantage_subset_missing(access):
    sheet = _sheet()
    sheet["core"]["permanent_defenses"]["condition_advantages"] = [
        {"condition": "poisoned", "effect": "avoid_or_end"}]
    sheet["modifier"]["effective_defenses"]["condition_advantages"] = []
    assert "defense-subset-violation" in _codes(sheet, access)


# ── state-gated resistance materialization (T44b) ─────────────────────────────


def _rage_like_state():
    return {"state": "active-a", "source": "State Feature A", "source_type": "feature"}


def test_state_resistance_missing_fires(access):
    """An active state whose owner grants a condition-gated resistance not on the
    sheet flags state-resistance-missing (incomplete)."""
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [_rage_like_state()]
    assert "state-resistance-missing" in _codes(sheet, access)


def test_state_resistance_present_passes(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [_rage_like_state()]
    sheet["modifier"]["effective_defenses"]["resistances"] = ["fire", "cold"]
    assert "state-resistance-missing" not in _codes(sheet, access)


def test_state_resistance_unresolved_owner_no_false_positive(access):
    sheet = _sheet()
    sheet["modifier"]["character_states"] = [
        {"state": "active-a", "source": "No Such Feature", "source_type": "feature"}]
    assert "state-resistance-missing" not in _codes(sheet, access)


# ── effective size (T44b) ─────────────────────────────────────────────────────


def test_size_step_mismatch_fires(access):
    sheet = _sheet()
    sheet["core"]["identity"]["size"] = "size-a"  # ordinal 3
    sheet["modifier"]["character_states"] = [
        {"state": "sized", "source": "Spell-Grow", "source_type": "spell",
         "detail": {"effect": "grow"}}]
    sheet["modifier"]["effective_size"] = "size-a"  # should be size-l
    assert "size-mismatch" in _codes(sheet, access)


def test_size_step_match_passes(access):
    sheet = _sheet()
    sheet["core"]["identity"]["size"] = "size-a"
    sheet["modifier"]["character_states"] = [
        {"state": "sized", "source": "Spell-Grow", "source_type": "spell",
         "detail": {"effect": "grow"}}]
    sheet["modifier"]["effective_size"] = "size-l"
    assert "size-mismatch" not in _codes(sheet, access)


def test_size_set_from_creature_match_passes(access):
    sheet = _sheet()
    sheet["core"]["identity"]["size"] = "size-a"
    sheet["modifier"]["character_states"] = [
        {"state": "shaped", "source": "Spell-Grow", "source_type": "spell",
         "detail": {"into": "creat-a"}}]
    sheet["modifier"]["effective_size"] = "size-l"
    assert "size-mismatch" not in _codes(sheet, access)


def test_size_no_state_default_matches_core(access):
    sheet = _sheet()
    sheet["core"]["identity"]["size"] = "size-a"
    sheet["modifier"]["effective_size"] = "size-a"
    assert "size-mismatch" not in _codes(sheet, access)


# ── attack damage rider (T44b) ────────────────────────────────────────────────


def _grow_sheet(damage: str, state_id="grown"):
    sheet = _sheet()
    sheet["modifier"]["attacks"] = [{"name": "Weapon A", "attack_bonus": 0, "damage": damage}]
    sheet["modifier"]["character_states"] = [
        {"state": state_id, "source": "Spell-Grow", "source_type": "spell"}]
    return sheet


def test_grow_rider_missing_fires(access):
    assert "attack-damage-rider-missing" in _codes(_grow_sheet("1d12+2"), access)


def test_grow_rider_present_passes(access):
    assert "attack-damage-rider-missing" not in _codes(_grow_sheet("1d12+2+1d4"), access)


def test_shrink_rider_missing_fires(access):
    assert "attack-damage-rider-missing" in _codes(_grow_sheet("1d12+2", "shrunk"), access)


def test_shrink_rider_present_passes(access):
    assert "attack-damage-rider-missing" not in _codes(_grow_sheet("1d12+2-1d4", "shrunk"), access)


def test_no_rider_expected_without_state(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"] = [{"name": "Weapon A", "attack_bonus": 0, "damage": "1d12+2"}]
    assert "attack-damage-rider-missing" not in _codes(sheet, access)


def test_rider_not_asserted_on_non_weapon_attack(access):
    """An attack whose name is not a weapon (e.g. a spell entry the deriver never folded a
    rider into) must not false-positive rider-missing, even with a rider-granting state active."""
    sheet = _grow_sheet("2d6")
    sheet["modifier"]["attacks"] = [{"name": "Not A Weapon", "attack_bonus": 0, "damage": "2d6"}]
    assert "attack-damage-rider-missing" not in _codes(sheet, access)


def test_rider_terms_deduped(access):
    """Two active states yielding the same rider term produce a single violation, not one per
    contributing state."""
    sheet = _grow_sheet("1d12+2")
    sheet["modifier"]["character_states"] = [
        {"state": "grown", "source": "Spell-Grow", "source_type": "spell"},
        {"state": "grown", "source": "Spell-Grow", "source_type": "spell"},
    ]
    misses = [x for x in check(sheet, access) if x.code == "attack-damage-rider-missing"]
    assert len(misses) == 1


# ── item-owned extra-damage rider (T51) ──────────────────────────────────────


def _blade_sheet(damage, attuned=True):
    """A sheet wielding the attuned magic weapon 'Blade Alpha' (mi-blade) in main_hand. mi-blade
    owns a single extra_damage grant (+1d6) and requires attunement."""
    sheet = _sheet()
    sheet["core"]["proficiencies"] = {"armor": [], "weapons": ["martial weapons"], "tools": []}
    sheet["inventory"] = {"equipped": {"main_hand": {"id": "w-main", "name": "Blade Alpha"}}}
    if attuned:
        sheet["modifier"]["item_states"] = [{"inventory_ref": "w-main", "attuned": True}]
    sheet["modifier"]["attacks"] = [{"name": "Blade Alpha", "attack_bonus": 0, "damage": damage}]
    return sheet


def test_item_rider_missing_from_own_attack_fires(access):
    """An attuned magic weapon's +1d6 rider absent from ITS OWN attack's damage is flagged."""
    assert "item-attack-damage-rider-missing" in _codes(_blade_sheet("1d8+2"), access)


def test_item_rider_present_passes(access):
    assert "item-attack-damage-rider-missing" not in _codes(_blade_sheet("1d8+2+1d6"), access)


def test_item_rider_not_required_when_not_attuned(access):
    """mi-blade requires attunement: without an attuned item_state the rider is not required."""
    assert "item-attack-damage-rider-missing" not in _codes(_blade_sheet("1d8+2", attuned=False), access)


def test_item_rider_not_flagged_on_different_weapon(access):
    """The item's rider is weapon-specific: a different equipped weapon's attack must never be
    flagged for it. Here Blade Alpha's own rider IS missing (one violation), and the Weapon A's
    attack (no rider owed) stays clean."""
    sheet = _blade_sheet("1d8+2")  # Blade Alpha missing its rider -> exactly one violation
    sheet["inventory"]["equipped"]["off_hand"] = {"id": "w-off", "name": "Weapon A"}
    sheet["modifier"]["attacks"].append(
        {"name": "Weapon A", "attack_bonus": 0, "damage": "1d12+2"})
    misses = [x for x in check(sheet, access) if x.code == "item-attack-damage-rider-missing"]
    assert len(misses) == 1
    assert "Blade Alpha" in misses[0].message


# ── stats-less magic weapon attack validation (T56) ──────────────────────────


def _relic_sheet(attack_bonus, damage):
    """A sheet wielding 'Relic Blade Alpha' (mi-relic-blade) in main_hand: a magic weapon with no
    base stats row, backed by base weapon-a (martial 1d12), owning one ungated +1d6 rider, no
    attunement. The validator resolves the base facts to re-derive the attack (F05-T56)."""
    sheet = _sheet()
    sheet["core"]["proficiencies"] = {"armor": [], "weapons": ["martial weapons"], "tools": []}
    sheet["inventory"] = {"equipped": {"main_hand": {"id": "w-relic", "name": "Relic Blade Alpha"}}}
    sheet["modifier"]["abilities"]["strength"] = {"modifier": 2, "reduction": 0}
    sheet["modifier"]["abilities"]["dexterity"] = {"modifier": 3, "reduction": 0}
    sheet["modifier"]["attacks"] = [
        {"name": "Relic Blade Alpha", "attack_bonus": attack_bonus, "damage": damage}]
    return sheet


def test_stats_less_magic_weapon_attack_validated(access):
    """The validator re-derives the base-weapon facts for a stats-less magic weapon and passes a
    correct attack (Str 2 + PB 2) carrying the item's +1d6 rider."""
    codes = _codes(_relic_sheet(4, "1d12+2+1d6"), access)
    assert "attack-bonus-mismatch" not in codes
    assert "item-attack-damage-rider-missing" not in codes


def test_stats_less_magic_weapon_wrong_bonus_fires(access):
    """A wrong attack bonus on a stats-less magic weapon is now caught (previously skipped as the
    weapon had no direct stats row)."""
    assert "attack-bonus-mismatch" in _codes(_relic_sheet(99, "1d12+2+1d6"), access)


def test_stats_less_magic_weapon_missing_rider_fires(access):
    """The item's own +1d6 rider missing from its materialised attack is flagged."""
    assert "item-attack-damage-rider-missing" in _codes(_relic_sheet(4, "1d12+2"), access)


# ── multi-row item extra-damage disambiguation (T57) ─────────────────────────


def _multi_blade_sheet(name, damage):
    """A sheet wielding a magic weapon that owns multiple extra_damage rows, in main_hand (no
    attunement). The validator re-derives the disambiguation and asserts the single ungated rider."""
    sheet = _sheet()
    sheet["core"]["proficiencies"] = {"armor": [], "weapons": ["martial weapons"], "tools": []}
    sheet["inventory"] = {"equipped": {"main_hand": {"id": "w-multi", "name": name}}}
    sheet["modifier"]["abilities"]["strength"] = {"modifier": 2, "reduction": 0}
    sheet["modifier"]["abilities"]["dexterity"] = {"modifier": 3, "reduction": 0}
    sheet["modifier"]["attacks"] = [{"name": name, "attack_bonus": 4, "damage": damage}]
    return sheet


def test_multi_row_item_ungated_rider_asserted(access):
    """The validator asserts the single ungated rider (+1d6) of a multi-row item; the gated +3d6
    variant is not required (F05-T57)."""
    codes = _codes(_multi_blade_sheet("Multi Blade Alpha", "1d8+2+1d6"), access)
    assert "item-attack-damage-rider-missing" not in codes


def test_multi_row_item_missing_ungated_rider_fires(access):
    """The single ungated rider missing from a multi-row item's own attack is flagged."""
    assert "item-attack-damage-rider-missing" in _codes(
        _multi_blade_sheet("Multi Blade Alpha", "1d8+2"), access)


def test_multi_row_item_gated_variant_not_required(access):
    """The gated +3d6 variant must NOT be demanded on the always-on attack — only the ungated rider
    is asserted, so an attack carrying just +1d6 is clean."""
    codes = _codes(_multi_blade_sheet("Multi Blade Alpha", "1d8+2+1d6"), access)
    assert "item-attack-damage-rider-missing" not in codes


def test_two_ungated_rows_assert_nothing(access):
    """Two ungated rows are ambiguous — the validator asserts no item rider at all (never sums)."""
    codes = _codes(_multi_blade_sheet("Twin Blade Alpha", "1d8+2"), access)
    assert "item-attack-damage-rider-missing" not in codes


# ── effective-CON max-HP recompute (T50) ─────────────────────────────────────


def _access_with_con(access):
    """Return an access wired to this test's isolated DB after aliasing a3's abbrev to 'con', so the
    HP recompute resolves a3 as the constitution ability (the shared synthetic table only carries the
    x1..x6 abbrevs). rules_db is rebuilt fresh per test, so this doesn't leak to other tests."""
    import sqlite3
    from access.validator import ValidatorAccess
    con = sqlite3.connect(access.db.path)
    con.execute("UPDATE ability SET abbrev='con' WHERE id='a3'")
    con.commit()
    con.close()
    return ValidatorAccess(path=access.db.path)


def _hp_sheet(con_final=12, level=3, vigor=True, states=None, max_boost=0, max_reduction=0):
    """A multi-level character with a constitution ability (a3). Optionally attunes the CON-set
    'Vigor Alpha' (sets a3 to 18) and/or carries active states."""
    sheet = _sheet()
    sheet["core"]["identity"] = {"size": "medium",
                                 "classes": [{"class": "Class A", "level": level}]}
    sheet["core"]["abilities"]["a3"] = {"final": con_final}
    if vigor:
        sheet["inventory"] = {"equipped": {"neck": {"id": "item-neck", "name": "Vigor Alpha"}}}
        sheet["modifier"]["item_states"] = [{"inventory_ref": "item-neck", "attuned": True}]
    if states is not None:
        sheet["modifier"]["character_states"] = states
    sheet["modifier"]["hit_points"]["max_boost"] = max_boost
    sheet["modifier"]["hit_points"]["max_reduction"] = max_reduction
    return sheet


def test_hp_boost_missing_from_con_set_item_fires(access):
    """An attuned CON-set item raises effective CON (+1 mod × level), but max_boost still 0 -> flag."""
    access = _access_with_con(access)
    # con 12 (mod +1) -> set 18 (mod +4); delta = (4-1)*3 = 9
    assert "hp-max-boost-mismatch" in _codes(_hp_sheet(con_final=12, level=3, max_boost=0), access)


def test_hp_boost_correct_delta_passes(access):
    access = _access_with_con(access)
    assert "hp-max-boost-mismatch" not in _codes(_hp_sheet(con_final=12, level=3, max_boost=9), access)


def test_hp_reduction_on_lower_override(access):
    """A 'set' that LOWERS effective CON drives the delta into max_reduction, not max_boost."""
    access = _access_with_con(access)
    # con 20 (mod +5) -> set 18 (mod +4); delta = (4-5)*3 = -3 -> reduction 3, boost 0
    assert "hp-max-reduction-mismatch" not in _codes(
        _hp_sheet(con_final=20, level=3, max_boost=0, max_reduction=3), access)
    assert "hp-max-reduction-mismatch" in _codes(
        _hp_sheet(con_final=20, level=3, max_boost=0, max_reduction=0), access)


def test_hp_state_grant_combined_with_delta(access):
    """max_boost must combine the state grant_hp contribution WITH the CON-delta."""
    access = _access_with_con(access)
    state = {"state": "hp-active", "source": "HP State Feature A", "source_type": "feature"}
    # state feature grants +5, CON delta = 9 -> expected max_boost 14
    assert "hp-max-boost-mismatch" not in _codes(
        _hp_sheet(con_final=12, level=3, states=[state], max_boost=14), access)
    assert "hp-max-boost-mismatch" in _codes(
        _hp_sheet(con_final=12, level=3, states=[state], max_boost=9), access)  # forgot the state


def test_hp_non_state_grant_inert(access):
    """An always-on (non-state) grant_hp (feat-gen +7) must NOT contribute to max_boost — only the
    CON delta (9) does, so a sheet with max_boost 9 is clean despite feat-gen owning a grant_hp."""
    access = _access_with_con(access)
    assert "hp-max-boost-mismatch" not in _codes(_hp_sheet(con_final=12, level=3, max_boost=9), access)


# ── state-gated max-HP reduction (drain/curse) (T58) ─────────────────────────


def test_state_gated_max_hp_reduction_expected(access):
    """The HP check re-derives a state-gated max-HP drain: the 'drained' state's owner has a −6
    grant_hp, so max_reduction 6 is clean and 0 is flagged (F05-T58)."""
    access = _access_with_con(access)
    state = {"state": "drained", "source": "HP Drain Feature A", "source_type": "feature"}
    # con 12, level 3, no CON-changing item -> CON delta 0; the drain drives max_reduction 6.
    assert "hp-max-reduction-mismatch" not in _codes(
        _hp_sheet(con_final=12, level=3, vigor=False, states=[state], max_reduction=6), access)
    assert "hp-max-reduction-mismatch" in _codes(
        _hp_sheet(con_final=12, level=3, vigor=False, states=[state], max_reduction=0), access)


def test_max_hp_reduction_gate_no_leak_in_check(access):
    """A reduction gated to a different state id must not be expected for the 'drained' state."""
    access = _access_with_con(access)
    state = {"state": "drained", "source": "HP Drain Feature B", "source_type": "feature"}
    assert "hp-max-reduction-mismatch" not in _codes(
        _hp_sheet(con_final=12, level=3, vigor=False, states=[state], max_reduction=0), access)


# ── VARIABLE state-gated max-HP drain: live-play amount, bounds-checked (T112) ─


def _var_drain_state():
    return {"state": "drained-var", "source": "HP Drain Feature C", "source_type": "feature"}


def test_variable_drain_within_bounds_passes(access):
    """A VARIABLE drain (2d6 → bounds [2, 12]) is a live-play amount: a max_reduction inside the dice
    bounds is clean, and the exact-equality reduction check is suspended (not fabricated) (F05-T112)."""
    access = _access_with_con(access)
    codes = _codes(_hp_sheet(con_final=12, level=3, vigor=False,
                             states=[_var_drain_state()], max_reduction=6), access)
    assert "hp-drain-out-of-bounds" not in codes
    assert "hp-max-reduction-mismatch" not in codes   # exact check suspended for a variable drain


def test_variable_drain_below_min_flagged(access):
    access = _access_with_con(access)
    assert "hp-drain-out-of-bounds" in _codes(
        _hp_sheet(con_final=12, level=3, vigor=False,
                  states=[_var_drain_state()], max_reduction=1), access)   # below 2d6 min (2)


def test_variable_drain_above_max_flagged(access):
    access = _access_with_con(access)
    assert "hp-drain-out-of-bounds" in _codes(
        _hp_sheet(con_final=12, level=3, vigor=False,
                  states=[_var_drain_state()], max_reduction=13), access)  # above 2d6 max (12)


def test_variable_drain_below_floor_flagged(access):
    """The book floor — the drain can't reduce the Hit Point maximum below 1 — is enforced even for an
    in-bounds reduction (F05-T112)."""
    access = _access_with_con(access)
    sheet = _hp_sheet(con_final=12, level=3, vigor=False,
                      states=[_var_drain_state()], max_reduction=12)      # in bounds [2, 12]
    sheet["core"]["hit_points"] = {"max": 10}                             # effective max 10-12 = -2
    assert "hp-drain-below-floor" in _codes(sheet, access)


def _transform_state():
    """A self-transform (physical) into a concrete synthetic form, mirroring the transform fixtures."""
    return {"state": "shaped", "source": "Spell-Grow", "source_type": "spell",
            "detail": {"into": "creature-form", "transform": "physical"}}


def test_variable_drain_under_transform_ignores_con_delta(access):
    """A simultaneous variable drain + self-transform must not double-count the CON delta the deriver
    zeroes under transform (T60). The drain-bounds check must honour the same 0-CON-delta rule as the
    max-HP check, so an in-bounds live drain stays clean instead of spuriously flagging out-of-bounds
    (T112). Without the transform-aware fork the miscounted CON base pulls the drain below its dice
    minimum and fires a false hp-drain-out-of-bounds."""
    access = _access_with_con(access)
    # core CON 22 (mod +6); Vigor sets 18 (mod +4): a −6 CON delta at level 3 the transform zeroes.
    sheet = _hp_sheet(con_final=22, level=3, vigor=True,
                      states=[_transform_state(), _var_drain_state()], max_reduction=6)
    assert "hp-drain-out-of-bounds" not in _codes(sheet, access)


def test_variable_drain_floor_ok_passes(access):
    access = _access_with_con(access)
    sheet = _hp_sheet(con_final=12, level=3, vigor=False,
                      states=[_var_drain_state()], max_reduction=6)
    sheet["core"]["hit_points"] = {"max": 20}                             # effective max 20-6 = 14 >= 1
    codes = _codes(sheet, access)
    assert "hp-drain-below-floor" not in codes and "hp-drain-out-of-bounds" not in codes


# ── starting treasure (re-derived from the chosen equipment bundle) ───────────


def test_starting_treasure_matches_both_bundles_passes(access):
    """When the sheet records both chosen bundle ids, the starting coin gp is re-derived as the SUM of
    both bundles' gp grants in the DB. Class bundle 'sa-b' grants 50 gp and background bundle
    'sa-bg-gp' grants 20 gp, so a treasure of 70 gp is consistent and passes."""
    sheet = _sheet()
    sheet["modifier"]["start_equipment_option"] = {"class": "sa-b", "background": "sa-bg-gp"}
    sheet["modifier"]["treasure"] = {"pp": 0, "gp": 70, "ep": 0, "sp": 0, "cp": 0}
    assert "starting-treasure-mismatch" not in _codes(sheet, access)


def test_starting_treasure_single_bundle_passes(access):
    """A build with only a class bundle re-derives from that bundle alone. 'sa-a' grants 15 gp."""
    sheet = _sheet()
    sheet["modifier"]["start_equipment_option"] = {"class": "sa-a"}
    sheet["modifier"]["treasure"] = {"pp": 0, "gp": 15, "ep": 0, "sp": 0, "cp": 0}
    assert "starting-treasure-mismatch" not in _codes(sheet, access)


def test_starting_treasure_mismatch_flags(access):
    """Recorded bundles whose summed DB gp grant disagrees with the sheet's coin gp are flagged."""
    sheet = _sheet()
    sheet["modifier"]["start_equipment_option"] = {"class": "sa-b", "background": "sa-bg-gp"}
    sheet["modifier"]["treasure"] = {"pp": 0, "gp": 99, "ep": 0, "sp": 0, "cp": 0}  # expected 70
    assert "starting-treasure-mismatch" in _codes(sheet, access)


def test_starting_treasure_dormant_without_bundle_id(access):
    """With no recorded bundle ids the branch is dormant: even a coin gp that matches no bundle is not
    flagged by this check (nothing to re-derive against)."""
    sheet = _sheet()
    sheet["modifier"]["treasure"] = {"pp": 0, "gp": 99, "ep": 0, "sp": 0, "cp": 0}
    assert "starting-treasure-mismatch" not in _codes(sheet, access)


def test_starting_treasure_unknown_bundle_id_skipped(access):
    """An unresolvable bundle id cannot be fully re-derived against, so the branch skips (no flag)."""
    sheet = _sheet()
    sheet["modifier"]["start_equipment_option"] = {"class": "sa-b", "background": "no-such-bundle"}
    sheet["modifier"]["treasure"] = {"pp": 0, "gp": 99, "ep": 0, "sp": 0, "cp": 0}
    assert "starting-treasure-mismatch" not in _codes(sheet, access)


# ── smoke ────────────────────────────────────────────────────────────────────


def test_smoke_not_in_all_checks(access):
    cnames = [c.__module__.split(".")[-1] for c in ALL_CHECKS]
    assert "modifier" not in cnames
