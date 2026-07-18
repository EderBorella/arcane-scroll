"""Tests for the MODIFIER validator's independent re-derivation of effect-granted attacks (T128).

Content-neutral: the synthetic self-buff spell (Spell Natwep) owns a grant_attack row whose
'spellcasting' ability_mode resolves to class-a's spellcasting ability (a1). The check re-derives
the granted attack from grant_attack — never from the deriver's output."""
from validator.checks.modifier import check


def _sheet(**mod_overrides):
    """A minimal MODIFIER sheet for a class-a caster with an active self-buff granting a natural
    weapon. The granted attack is authored CORRECTLY by default: a1 modifier (2) + PB (2) = 4 to
    hit, 1d6+2 damage, type poison (from the grant row)."""
    core = {
        "identity": {"size": "medium",
                     "classes": [{"class": "Class A", "level": 3, "subclass": None}]},
        "abilities": {"a1": {"final": 14}, "a2": {"final": 16}, "a3": {"final": 12}},
        "proficiency_bonus": 2,
        "saving_throws": {"a1": {"proficient": True}, "a2": {"proficient": False},
                          "a3": {"proficient": True}},
        "skills": {"sk1": {"ability": "a1", "proficient": True, "expertise": False}},
        "permanent_defenses": {"resistances": [], "immunities": [], "vulnerabilities": [],
                               "condition_immunities": [], "save_advantages": [],
                               "condition_advantages": []},
        "features": [], "feats": [],
    }
    modifier = {
        "schema_version": 1, "character_id": "t", "character_name": "T",
        "xp": 0, "treasure": {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0},
        "hit_points": {"current": 22, "temp": 0, "max_boost": 0, "max_reduction": 0},
        "death_saves": {"successes": 0, "failures": 0},
        "hit_dice": {"d8": {"remaining": 3}},
        "spell_slots": {"1": {"remaining": 4}}, "pact_slots": {"1": {"remaining": 0}},
        "resource_state": {},
        "abilities": {"a1": {"modifier": 2, "reduction": 0},
                      "a2": {"modifier": 3, "reduction": 0},
                      "a3": {"modifier": 1, "reduction": 0}},
        "saving_throws": {"a1": {"modifier": 4}, "a2": {"modifier": 3}, "a3": {"modifier": 3}},
        "skills": {"sk1": {"modifier": 4}},
        "passive_scores": {"sk1": 14},
        "effective_senses": {},
        "effective_defenses": {"resistances": [], "immunities": [], "vulnerabilities": [],
                               "condition_immunities": [], "save_advantages": [],
                               "condition_advantages": []},
        "effective_size": "medium",
        "effective_abilities": {"a1": 14, "a2": 16, "a3": 12},
        "armor_class": 13,
        "armor_class_detail": {"source": "unarmored", "base": 10, "dex_bonus": 3,
                               "bonuses": [], "floor": None},
        "initiative": 3, "speed": {"walk": 30},
        "speed_detail": {"base": 30, "base_source": "species", "base_mode": "walk", "modifiers": []},
        "attacks": [{"name": "Attack Alpha", "attack_bonus": 4, "damage": "1d6+2",
                     "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        "character_states": [{"state": "altered", "source": "Spell Natwep", "source_type": "spell",
                              "detail": {"option": "natural_weapons"}}],
        "item_states": [],
        "features": [], "feats": [], "prepared_spells": [],
    }
    modifier.update(mod_overrides)
    return {"core": core, "inventory": {}, "grimoire": {"spells": []}, "modifier": modifier}


def _granted_codes(sheet, access):
    return {v.code for v in check(sheet, access) if v.code.startswith("granted-attack")}


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_correct_granted_attack_passes(access):
    assert _granted_codes(_sheet(), access) == set()


def test_missing_granted_attack_flagged(access):
    sheet = _sheet(attacks=[])
    assert "granted-attack-missing" in _granted_codes(sheet, access)


def test_wrong_attack_bonus_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["attack_bonus"] = 99
    assert "granted-attack-bonus-mismatch" in _granted_codes(sheet, access)


def test_wrong_damage_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["damage"] = "1d6+99"
    assert "granted-attack-damage-mismatch" in _granted_codes(sheet, access)


def test_wrong_damage_type_flagged(access):
    sheet = _sheet()
    sheet["modifier"]["attacks"][0]["damage_type"] = "fire"
    assert "granted-attack-type-mismatch" in _granted_codes(sheet, access)


def test_no_state_no_granted_attack_check(access):
    """With no active state the granted-attack check is inert (no owner to read a grant from)."""
    sheet = _sheet(character_states=[], attacks=[])
    assert _granted_codes(sheet, access) == set()


# ── non-spellcasting ability_mode resolution (T136) ──────────────────────────


def _strmode_state():
    return [{"state": "buffed", "source": "Spell Str Mode", "source_type": "spell", "detail": {}}]


def _finmode_state():
    return [{"state": "buffed", "source": "Spell Fin Mode", "source_type": "spell", "detail": {}}]


def _str_dex(strength: int, dexterity: int) -> dict:
    return {"strength": {"modifier": strength, "reduction": 0},
            "dexterity": {"modifier": dexterity, "reduction": 0}}


def test_strength_mode_granted_attack_passes(access):
    """A strength-mode grant re-derives to the Strength modifier (2) + PB (2) = 4, damage 1d8+2."""
    sheet = _sheet(
        abilities=_str_dex(2, 4),
        attacks=[{"name": "Attack Str", "attack_bonus": 4, "damage": "1d8+2",
                  "damage_type": "poison", "weapon_mastery": None, "properties": ["light"]}],
        character_states=_strmode_state())
    assert _granted_codes(sheet, access) == set()


def test_finesse_mode_picks_dexterity_when_higher(access):
    """Finesse re-derives to max(STR 2, DEX 4) = 4 + PB = 6, damage 1d4+4."""
    sheet = _sheet(
        abilities=_str_dex(2, 4),
        attacks=[{"name": "Attack Fin", "attack_bonus": 6, "damage": "1d4+4",
                  "damage_type": "fire", "weapon_mastery": None, "properties": []}],
        character_states=_finmode_state())
    assert _granted_codes(sheet, access) == set()


def test_finesse_mode_picks_strength_when_higher(access):
    """Finesse re-derives to max(STR 5, DEX 1) = 5 + PB = 7, damage 1d4+5."""
    sheet = _sheet(
        abilities=_str_dex(5, 1),
        attacks=[{"name": "Attack Fin", "attack_bonus": 7, "damage": "1d4+5",
                  "damage_type": "fire", "weapon_mastery": None, "properties": []}],
        character_states=_finmode_state())
    assert _granted_codes(sheet, access) == set()


def test_strength_mode_wrong_bonus_flagged(access):
    sheet = _sheet(
        abilities=_str_dex(2, 4),
        attacks=[{"name": "Attack Str", "attack_bonus": 99, "damage": "1d8+2",
                  "damage_type": "poison", "weapon_mastery": None, "properties": ["light"]}],
        character_states=_strmode_state())
    assert "granted-attack-bonus-mismatch" in _granted_codes(sheet, access)


# ── permanent-owner granted attack (always-on, no state) ─────────────────────


def _with_owner_feat(sheet):
    """Add the granting feat (a permanent owner) to CORE.feats so the permanent-owner pass reads it."""
    sheet["core"]["feats"] = [{"name": "Feat Owner Atk", "source": "bg-a"}]
    return sheet


def test_permanent_owner_granted_attack_passes(access):
    """A feat-owned finesse grant is re-derived from the permanent-owner pass (no active state):
    max(STR 1, DEX 3) = 3 + PB 2 = 5, damage 1d6+3."""
    sheet = _with_owner_feat(_sheet(
        abilities=_str_dex(1, 3),
        attacks=[{"name": "Attack Owner", "attack_bonus": 5, "damage": "1d6+3",
                  "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        character_states=[]))
    assert _granted_codes(sheet, access) == set()


def test_permanent_owner_granted_attack_missing_flagged(access):
    """The feat's attack is required even with no active state; omitting it is flagged incomplete."""
    sheet = _with_owner_feat(_sheet(abilities=_str_dex(1, 3), attacks=[], character_states=[]))
    assert "granted-attack-missing" in _granted_codes(sheet, access)


# ── item-owned granted attack (T134) ─────────────────────────────────────────


def _item_sheet(item, attuned, attacks, abilities):
    """A MODIFIER sheet with one equipped magic item and no active state; the item pass reads the
    inventory via the annotated core view (attunement from item_states)."""
    sheet = _sheet(abilities=abilities, attacks=attacks, character_states=[])
    sheet["inventory"] = {"equipped": {"slot1": item}}
    if attuned:
        sheet["modifier"]["item_states"] = [{"inventory_ref": item["id"], "attuned": True}]
    return sheet


def test_item_attuned_granted_attack_passes(access):
    """An attuned item's strength-mode attack re-derives to STR 3 + PB 2 = 5, damage 1d8+3."""
    item = {"id": "it1", "name": "Claws Alpha", "magic": True}
    sheet = _item_sheet(item, True,
        attacks=[{"name": "Attack Claws", "attack_bonus": 5, "damage": "1d8+3",
                  "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(3, 1))
    assert _granted_codes(sheet, access) == set()


def test_item_attuned_granted_attack_missing_flagged(access):
    item = {"id": "it1", "name": "Claws Alpha", "magic": True}
    sheet = _item_sheet(item, True, attacks=[], abilities=_str_dex(3, 1))
    assert "granted-attack-missing" in _granted_codes(sheet, access)


def test_item_attunement_required_not_attuned_not_required(access):
    """An attunement-required item that is NOT attuned confers no required attack."""
    item = {"id": "it1", "name": "Claws Alpha", "magic": True}
    sheet = _item_sheet(item, False, attacks=[], abilities=_str_dex(3, 1))
    assert _granted_codes(sheet, access) == set()


def test_item_passive_on_equip_granted_attack_passes(access):
    """A passive-on-equip item's finesse attack re-derives to max(STR 1, DEX 4) = 4 + PB 2 = 6,
    damage 1d6+4."""
    item = {"id": "it2", "name": "Fangs Alpha", "magic": True}
    sheet = _item_sheet(item, False,
        attacks=[{"name": "Attack Fangs", "attack_bonus": 6, "damage": "1d6+4",
                  "damage_type": "fire", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(1, 4))
    assert _granted_codes(sheet, access) == set()


# ── item weapon-bonus scoped to a granted attack (no cross-share) ────────────


def _weapon_sheet(equipped, item_states, attacks, abilities):
    """A MODIFIER sheet with several equipped items (each a dict with id/name/magic) + item_states,
    proficient with martial weapons so a real weapon attack re-derives with PB."""
    sheet = _sheet(abilities=abilities, attacks=attacks, character_states=[])
    sheet["core"]["proficiencies"] = {"armor": [], "weapons": ["martial weapons"], "tools": []}
    sheet["inventory"] = {"equipped": equipped}
    sheet["modifier"]["item_states"] = item_states
    return sheet


def test_scoped_bonus_applies_to_its_granted_attack_passes(access):
    """The item's scoped +1 folds into its granted attack: STR 2 + PB 2 + 1 = 5, damage 1d8+3."""
    sheet = _weapon_sheet(
        {"hands": {"id": "ig", "name": "Gauntlet Alpha", "magic": True}},
        [{"inventory_ref": "ig", "attuned": True}],
        attacks=[{"name": "Attack Gauntlet", "attack_bonus": 5, "damage": "1d8+3",
                  "damage_type": "slashing", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    assert _granted_codes(sheet, access) == set()


def test_scoped_bonus_does_not_leak_to_real_weapon(access):
    """The scoped +1 must not inflate a real weapon. Weapon A (martial 1d12, STR 2 + PB 2 = 4)
    authored WITHOUT the +1 is clean; authored WITH the leaked +1 is flagged."""
    equipped = {"hands": {"id": "ig", "name": "Gauntlet Alpha", "magic": True},
                "main_hand": {"id": "w1", "name": "Weapon A", "magic": False}}
    states = [{"inventory_ref": "ig", "attuned": True}]
    good = _weapon_sheet(equipped, states,
        attacks=[{"name": "Weapon A", "attack_bonus": 4, "damage": "1d12+2",
                  "damage_type": "slashing", "weapon_mastery": None, "properties": []},
                 {"name": "Attack Gauntlet", "attack_bonus": 5, "damage": "1d8+3",
                  "damage_type": "slashing", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    assert "attack-bonus-mismatch" not in _codes(good, access)
    assert _granted_codes(good, access) == set()

    leaked = _weapon_sheet(equipped, states,
        attacks=[{"name": "Weapon A", "attack_bonus": 5, "damage": "1d12+2",
                  "damage_type": "slashing", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    assert "attack-bonus-mismatch" in _codes(leaked, access)


def test_unscoped_weapon_bonus_applies_to_weapon_not_granted(access):
    """An UNSCOPED weapon bonus (Charm Alpha, +1 to every weapon attack) applies to Weapon A (STR 2
    + PB 2 + 1 = 5) but NOT to the item-granted Attack Claws (STR 2 + PB 2 = 4, 1d8+2)."""
    sheet = _weapon_sheet(
        {"waist": {"id": "ic", "name": "Charm Alpha", "magic": True},
         "hands": {"id": "iw", "name": "Claws Alpha", "magic": True},
         "main_hand": {"id": "w1", "name": "Weapon A", "magic": False}},
        [{"inventory_ref": "ic", "attuned": True}, {"inventory_ref": "iw", "attuned": True}],
        attacks=[{"name": "Weapon A", "attack_bonus": 5, "damage": "1d12+2",
                  "damage_type": "slashing", "weapon_mastery": None, "properties": []},
                 {"name": "Attack Claws", "attack_bonus": 4, "damage": "1d8+2",
                  "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    assert "attack-bonus-mismatch" not in _codes(sheet, access)
    assert _granted_codes(sheet, access) == set()


def test_scoped_bonus_does_not_bleed_onto_another_granted_attack(access):
    """A bonus scoped to granted attack A must not apply to a DIFFERENT granted attack B. The gauntlet
    grants A (scoped +1 → STR 2 + PB 2 + 1 = 5, 1d8+3); the claws grant B (no scoped bonus → STR 2 +
    PB 2 = 4, 1d8+2). Authoring B correctly passes; leaking the +1 onto B is flagged."""
    equipped = {"hands": {"id": "ig", "name": "Gauntlet Alpha", "magic": True},
                "off_hand": {"id": "ic", "name": "Claws Alpha", "magic": True}}
    states = [{"inventory_ref": "ig", "attuned": True}, {"inventory_ref": "ic", "attuned": True}]
    a_ok = {"name": "Attack Gauntlet", "attack_bonus": 5, "damage": "1d8+3",
            "damage_type": "slashing", "weapon_mastery": None, "properties": []}

    good = _weapon_sheet(equipped, states,
        attacks=[a_ok, {"name": "Attack Claws", "attack_bonus": 4, "damage": "1d8+2",
                        "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    assert _granted_codes(good, access) == set()

    leaked = _weapon_sheet(equipped, states,
        attacks=[a_ok, {"name": "Attack Claws", "attack_bonus": 5, "damage": "1d8+3",
                        "damage_type": "poison", "weapon_mastery": None, "properties": []}],
        abilities=_str_dex(2, 1))
    codes = _granted_codes(leaked, access)
    assert "granted-attack-bonus-mismatch" in codes
    assert "granted-attack-damage-mismatch" in codes


# ── multi-caster spellcasting-ability disambiguation (T135) ──────────────────

# class-cast1 casts with a1, class-cast2 with a2; abilities give a1→3, a2→5.
_C1 = {"class": "Class Cast1", "level": 3, "subclass": None}
_C2 = {"class": "Class Cast2", "level": 3, "subclass": None}


def _mc_sheet(classes, source, attack):
    sheet = _sheet(
        abilities={"a1": {"modifier": 3, "reduction": 0}, "a2": {"modifier": 5, "reduction": 0}},
        attacks=[attack],
        character_states=[{"state": "buffed", "source": source, "source_type": "spell",
                           "detail": {}}])
    sheet["core"]["identity"] = {"size": "medium", "classes": classes}
    return sheet


def test_mc_carrier_ability_carrier_first_passes(access):
    """Spell on cast1's list only, cast1 first → re-derives cast1's ability a1 (3) + PB 2 = 5."""
    sheet = _mc_sheet([_C1, _C2], "Spell MC Atk1",
        {"name": "Attack MC1", "attack_bonus": 5, "damage": "1d6+3",
         "damage_type": "poison", "weapon_mastery": None, "properties": []})
    assert _granted_codes(sheet, access) == set()


def test_mc_carrier_ability_regardless_of_order_passes(access):
    """Ordering independence: non-carrier cast2 first, carrier cast1 second → still a1 (5), not a2."""
    sheet = _mc_sheet([_C2, _C1], "Spell MC Atk1",
        {"name": "Attack MC1", "attack_bonus": 5, "damage": "1d6+3",
         "damage_type": "poison", "weapon_mastery": None, "properties": []})
    assert _granted_codes(sheet, access) == set()


def test_mc_wrong_when_using_first_listed_ability_flagged(access):
    """Proof the re-derivation is NOT 'first caster': with cast2 listed first, an attack authored from
    cast2's ability (a2 → bonus 7, 1d6+5) is flagged, because the carrier is cast1 (a1)."""
    sheet = _mc_sheet([_C2, _C1], "Spell MC Atk1",
        {"name": "Attack MC1", "attack_bonus": 7, "damage": "1d6+5",
         "damage_type": "poison", "weapon_mastery": None, "properties": []})
    codes = _granted_codes(sheet, access)
    assert "granted-attack-bonus-mismatch" in codes
    assert "granted-attack-damage-mismatch" in codes


def test_mc_spell_on_other_class_resolves_that_class_passes(access):
    """Spell on cast2's list only → re-derives cast2's ability a2 (5) + PB 2 = 7."""
    sheet = _mc_sheet([_C1, _C2], "Spell MC Atk2",
        {"name": "Attack MC2", "attack_bonus": 7, "damage": "1d6+5",
         "damage_type": "fire", "weapon_mastery": None, "properties": []})
    assert _granted_codes(sheet, access) == set()


def test_mc_single_caster_off_all_lists_falls_back_passes(access):
    """Single caster, granting spell off every class list → fallback keeps the first caster's a1 (3)."""
    sheet = _mc_sheet([_C1], "Spell Natwep",
        {"name": "Attack Alpha", "attack_bonus": 5, "damage": "1d6+3",
         "damage_type": "poison", "weapon_mastery": None, "properties": []})
    assert _granted_codes(sheet, access) == set()
