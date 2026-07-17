from validator.checks.inventory import check
from validator.checks import ALL_CHECKS
from validator.checks import inventory as inv_check


def _make_sheet(**overrides):
    sheet = {
        "equipped": {},
        "backpack": [],
        "modifier": None,
    }
    sheet.update(overrides)
    return sheet


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ── C-I1a: item identity ─────────────────────────────────────────────────────


def test_valid_empty(access):
    assert check(_make_sheet(), access) == []


def test_valid_single_weapon(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A"}},
    )
    assert check(sheet, access) == []


def test_valid_armor_shield(access):
    sheet = _make_sheet(
        equipped={
            "armor": {"id": "a1", "name": "armor-a"},
            "shield": {"id": "s1", "name": "Shield Alpha"},
        },
    )
    assert check(sheet, access) == []


def test_valid_backpack_items(access):
    sheet = _make_sheet(
        backpack=[
            {"id": "b1", "name": "Weapon A"},
            {"id": "b2", "name": "weapon-c"},
        ],
    )
    assert check(sheet, access) == []


def test_valid_magic_item(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "m1", "name": "Sword Alpha",
                          "template_item": "tpl-weapon-1", "base_item": "weapon-a"},
        },
    )
    assert check(sheet, access) == []


def test_valid_scroll(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Scroll Alpha", "spell_id": "sp1"}],
    )
    assert check(sheet, access) == []


def test_duplicate_id_equipped_backpack(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "dup", "name": "Weapon A"}},
        backpack=[{"id": "dup", "name": "weapon-c"}],
    )
    assert "duplicate-item-id" in _codes(sheet, access)


def test_duplicate_id_same_backpack(access):
    sheet = _make_sheet(
        backpack=[
            {"id": "dup", "name": "Weapon A"},
            {"id": "dup", "name": "weapon-c"},
        ],
    )
    assert "duplicate-item-id" in _codes(sheet, access)


def test_unknown_catalog_item(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Nonexistent Item"}},
    )
    assert "unknown-catalog-item" in _codes(sheet, access)


def test_known_catalog_item(access):
    sheet = _make_sheet(
        backpack=[{"id": "b1", "name": "Weapon A"}],
    )
    assert "unknown-catalog-item" not in _codes(sheet, access)


def test_known_magic_item(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Sword Alpha"}},
    )
    assert "unknown-catalog-item" not in _codes(sheet, access)


# ── C-I1b: slot legality ─────────────────────────────────────────────────────


def test_invalid_slot_key(access):
    sheet = _make_sheet(
        equipped={"nonexistent_slot": {"id": "w1", "name": "Weapon A"}},
    )
    assert "invalid-slot" in _codes(sheet, access)


def test_two_handed_plus_shield(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "w1", "name": "Weapon A"},
            "off_hand": {"id": "s1", "name": "Shield Alpha", "category": "shield"},
        },
    )
    assert "two-handed-plus-shield" in _codes(sheet, access)


def test_two_handed_no_shield_valid(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A"}},
    )
    assert "two-handed-plus-shield" not in _codes(sheet, access)


def test_one_handed_with_shield_valid(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "w1", "name": "weapon-b"},
            "off_hand": {"id": "s1", "name": "Shield Alpha", "category": "shield"},
        },
    )
    assert "two-handed-plus-shield" not in _codes(sheet, access)


# ── C-I1c: template resolution ───────────────────────────────────────────────


def test_template_valid(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Sword Alpha",
                                "template_item": "tpl-weapon-1", "base_item": "weapon-a"}},
    )
    assert "invalid-template" not in _codes(sheet, access)


def test_template_wrong_kind(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Sword Alpha",
                                "template_item": "tpl-shield", "base_item": "weapon-a"}},
    )
    codes = _codes(sheet, access)
    assert "invalid-template" in codes


def test_template_unknown(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Sword Alpha",
                                "template_item": "nonexistent-template"}},
    )
    assert "invalid-template" in _codes(sheet, access)


# ── C-I1d: single-use casting item integrity ─────────────────────────────────


def test_casting_consumable_invalid_spell(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Scroll Alpha", "spell_id": "nonexistent-spell"}],
    )
    assert "invalid-casting-consumable" in _codes(sheet, access)


def test_casting_consumable_valid(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Scroll Alpha", "spell_id": "sp1"}],
    )
    assert "invalid-casting-consumable" not in _codes(sheet, access)


# ── C-I1e: consumable attribution ────────────────────────────────────────────


def test_consumable_missing(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A"}},
        modifier={"item_states": [
            {"inventory_ref": "not-found", "consumable": True},
        ]},
    )
    assert "consumable-missing-inventory" in _codes(sheet, access)


def test_consumable_present(access):
    sheet = _make_sheet(
        backpack=[{"id": "scroll1", "name": "Scroll Alpha", "spell_id": "sp1"}],
        modifier={"item_states": [
            {"inventory_ref": "scroll1", "consumable": True},
        ]},
    )
    assert "consumable-missing-inventory" not in _codes(sheet, access)


def test_no_modifier_no_consumable_check(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A"}},
    )
    assert "consumable-missing-inventory" not in _codes(sheet, access)


# ── smoke ────────────────────────────────────────────────────────────────────


def test_smoke_all_checks_registered(access):
    cnames = [c.__module__.split(".")[-1] for c in ALL_CHECKS]
    assert "spellcasting" in cnames
    # inventory is inventory:1-specific, not in ALL_CHECKS (v10 sheets have equipped)
    assert "inventory" not in cnames


def test_malformed_no_crash(access):
    sheet = _make_sheet(
        equipped="not a dict",
        backpack="not a list",
    )
    assert isinstance(check(sheet, access), list)


def test_null_spell_id_no_crash(access):
    sheet = _make_sheet(
        backpack=[{"id": "b1", "name": "Weapon A", "spell_id": None}],
    )
    assert "invalid-casting-consumable" not in _codes(sheet, access)


# ── C-I1b2: equipped-slot grounding (F05-T102) ───────────────────────────────


def test_weapon_in_armor_slot_fires(access):
    sheet = _make_sheet(equipped={"armor": {"id": "w1", "name": "Weapon A"}})
    assert "slot-assignment-mismatch" in _codes(sheet, access)


def test_worn_armor_in_hand_fires(access):
    sheet = _make_sheet(equipped={"main_hand": {"id": "a1", "name": "Armor A"}})
    assert "slot-assignment-mismatch" in _codes(sheet, access)


def test_shield_in_main_hand_fires(access):
    sheet = _make_sheet(equipped={"main_hand": {"id": "s1", "name": "Shield"}})
    assert "slot-assignment-mismatch" in _codes(sheet, access)


def test_grounded_slots_valid_layout_passes(access):
    sheet = _make_sheet(equipped={
        "main_hand": {"id": "w1", "name": "Weapon A"},
        "armor": {"id": "a1", "name": "Armor A"},
        "shield": {"id": "s1", "name": "Shield"},
    })
    assert "slot-assignment-mismatch" not in _codes(sheet, access)


def test_slot_grounding_skips_magic_item(access):
    # a magic item's slot semantics are not DB-bound to a base category — never flagged
    sheet = _make_sheet(equipped={"armor": {"id": "m1", "name": "Sword Alpha"}})
    assert "slot-assignment-mismatch" not in _codes(sheet, access)


# ── C-I1b3: catalog-enrichment re-derivation (F05-T102) ──────────────────────


def test_wrong_weapon_damage_dice_fires(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A", "damage_dice": "1d6"}})
    assert "enrichment-mismatch" in _codes(sheet, access)


def test_wrong_weapon_damage_type_fires(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A", "damage_type": "piercing"}})
    assert "enrichment-mismatch" in _codes(sheet, access)


def test_extra_weapon_property_fires(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Weapon A", "properties": ["finesse"]}})
    assert "enrichment-mismatch" in _codes(sheet, access)


def test_wrong_shield_ac_bonus_fires(access):
    # gold errata analogue: a shield stated at +1 when the DB fact is +2
    sheet = _make_sheet(equipped={"shield": {"id": "s1", "name": "Shield", "ac_bonus": 1}})
    assert "enrichment-mismatch" in _codes(sheet, access)


def test_wrong_armor_dex_cap_fires(access):
    sheet = _make_sheet(equipped={"armor": {"id": "a1", "name": "Armor A", "dex_cap": 2}})
    assert "enrichment-mismatch" in _codes(sheet, access)


def test_correct_enrichment_passes(access):
    sheet = _make_sheet(equipped={
        "main_hand": {"id": "w1", "name": "Weapon A", "damage_dice": "1d12",
                      "damage_type": "slashing", "properties": ["two-handed"]},
        "shield": {"id": "s1", "name": "Shield", "ac_bonus": 2},
    })
    assert "enrichment-mismatch" not in _codes(sheet, access)


def test_enrichment_skips_magic_item(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Sword Alpha", "damage_dice": "9d9"}})
    assert "enrichment-mismatch" not in _codes(sheet, access)


def test_omitted_facts_not_flagged(access):
    # the sheet need not restate every catalogue fact — an omission is not a contradiction
    sheet = _make_sheet(equipped={"main_hand": {"id": "w1", "name": "Weapon A"}})
    assert "enrichment-mismatch" not in _codes(sheet, access)
