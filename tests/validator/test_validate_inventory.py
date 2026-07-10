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
        equipped={"main_hand": {"id": "w1", "name": "Greataxe"}},
    )
    assert check(sheet, access) == []


def test_valid_armor_shield(access):
    sheet = _make_sheet(
        equipped={
            "armor": {"id": "a1", "name": "chain-mail"},
            "shield": {"id": "s1", "name": "Magic Shield"},
        },
    )
    assert check(sheet, access) == []


def test_valid_backpack_items(access):
    sheet = _make_sheet(
        backpack=[
            {"id": "b1", "name": "Greataxe"},
            {"id": "b2", "name": "club"},
        ],
    )
    assert check(sheet, access) == []


def test_valid_magic_item(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "m1", "name": "Magic Sword",
                          "template_item": "tpl-weapon-1", "base_item": "greataxe"},
        },
    )
    assert check(sheet, access) == []


def test_valid_spell_scroll(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Magic Scroll", "spell_id": "sp1"}],
    )
    assert check(sheet, access) == []


def test_duplicate_id_equipped_backpack(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "dup", "name": "Greataxe"}},
        backpack=[{"id": "dup", "name": "club"}],
    )
    assert "duplicate-item-id" in _codes(sheet, access)


def test_duplicate_id_same_backpack(access):
    sheet = _make_sheet(
        backpack=[
            {"id": "dup", "name": "Greataxe"},
            {"id": "dup", "name": "club"},
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
        backpack=[{"id": "b1", "name": "Greataxe"}],
    )
    assert "unknown-catalog-item" not in _codes(sheet, access)


def test_known_magic_item(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Magic Sword"}},
    )
    assert "unknown-catalog-item" not in _codes(sheet, access)


# ── C-I1b: slot legality ─────────────────────────────────────────────────────


def test_invalid_slot_key(access):
    sheet = _make_sheet(
        equipped={"nonexistent_slot": {"id": "w1", "name": "Greataxe"}},
    )
    assert "invalid-slot" in _codes(sheet, access)


def test_two_handed_plus_shield(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "w1", "name": "Greataxe"},
            "off_hand": {"id": "s1", "name": "Magic Shield", "category": "shield"},
        },
    )
    assert "two-handed-plus-shield" in _codes(sheet, access)


def test_two_handed_no_shield_valid(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Greataxe"}},
    )
    assert "two-handed-plus-shield" not in _codes(sheet, access)


def test_one_handed_with_shield_valid(access):
    sheet = _make_sheet(
        equipped={
            "main_hand": {"id": "w1", "name": "handaxe"},
            "off_hand": {"id": "s1", "name": "Magic Shield", "category": "shield"},
        },
    )
    assert "two-handed-plus-shield" not in _codes(sheet, access)


# ── C-I1c: template resolution ───────────────────────────────────────────────


def test_template_valid(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Magic Sword",
                                "template_item": "tpl-weapon-1", "base_item": "greataxe"}},
    )
    assert "invalid-template" not in _codes(sheet, access)


def test_template_wrong_kind(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Magic Sword",
                                "template_item": "tpl-shield", "base_item": "greataxe"}},
    )
    codes = _codes(sheet, access)
    assert "invalid-template" in codes


def test_template_unknown(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "m1", "name": "Magic Sword",
                                "template_item": "nonexistent-template"}},
    )
    assert "invalid-template" in _codes(sheet, access)


# ── C-I1d: spell scroll integrity ────────────────────────────────────────────


def test_spell_scroll_invalid_spell(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Magic Scroll", "spell_id": "nonexistent-spell"}],
    )
    assert "invalid-spell-scroll" in _codes(sheet, access)


def test_spell_scroll_valid(access):
    sheet = _make_sheet(
        backpack=[{"id": "s1", "name": "Magic Scroll", "spell_id": "sp1"}],
    )
    assert "invalid-spell-scroll" not in _codes(sheet, access)


# ── C-I1e: consumable attribution ────────────────────────────────────────────


def test_consumable_missing(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Greataxe"}},
        modifier={"item_states": [
            {"inventory_ref": "not-found", "consumable": True},
        ]},
    )
    assert "consumable-missing-inventory" in _codes(sheet, access)


def test_consumable_present(access):
    sheet = _make_sheet(
        backpack=[{"id": "scroll1", "name": "Magic Scroll", "spell_id": "sp1"}],
        modifier={"item_states": [
            {"inventory_ref": "scroll1", "consumable": True},
        ]},
    )
    assert "consumable-missing-inventory" not in _codes(sheet, access)


def test_no_modifier_no_consumable_check(access):
    sheet = _make_sheet(
        equipped={"main_hand": {"id": "w1", "name": "Greataxe"}},
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
        backpack=[{"id": "b1", "name": "Greataxe", "spell_id": None}],
    )
    assert "invalid-spell-scroll" not in _codes(sheet, access)
