"""Equipment-derived: equipped armour (for armour-based AC), inventory assembly, and treasure."""
import random

from app.derivation import equipment


def test_equipped_armour_from_route(catalog):
    armour, shield = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Fighter", "level": 5}],
        "equipment_0": "Chain Mail", "equipment_1": "a martial weapon + Shield",
        "equipment_1_pick": ["Longsword"]})
    assert armour["name"] == "Chain Mail" and shield is True


def test_equipped_armour_picks_highest_base(catalog):
    armour, _ = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Fighter", "level": 5}], "equipment_0": "Leather Armor + Chain Mail"})
    assert armour["name"] == "Chain Mail"          # heavier of the two named


def test_half_plate_not_misread_as_plate(catalog):
    # "Plate Armor" ⊂ "Half Plate Armor" — must NOT pick the heavier Plate just because its name is a substring
    armour, _ = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Fighter", "level": 5}], "equipment_0": "Half Plate Armor"})
    assert armour["name"] == "Half Plate Armor"

    studded, _ = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Rogue", "level": 5}], "equipment_0": "Studded Leather Armor"})
    assert studded["name"] == "Studded Leather Armor"


def test_shield_not_false_positive_on_substring(catalog):
    # "a shielded lantern" must NOT register a shield (naked `"shield" in blob` would)
    _, shield = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Mage", "level": 5}], "equipment_0": "a wand and a shielded lantern"})
    assert shield is False
    # a genuine shield is still detected
    _, real = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Fighter", "level": 5}], "equipment_0": "a martial weapon + Shield"})
    assert real is True


def test_unarmoured_returns_none(catalog):
    armour, shield = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Mage", "level": 5}], "equipment_0": "Dagger", "equipment_1": "arcane focus"})
    assert armour is None and shield is False


def test_assemble_inventory_category_route(catalog):
    # warrior slot0 = direct category (WeaponA); slot1 union route carries its weapons inline
    choices = {"classes": [{"class": "warrior", "level": 3}],
               "equipment_0": "WeaponA",
               "equipment_1": {"route": "a martial weapon", "weapons": ["MartialA"]}}
    inv = {i["item"]: i["quantity"] for i in equipment.assemble_inventory(catalog, choices)}
    assert inv == {"WeaponA": 1, "MartialA": 1}


def test_assemble_inventory_concrete_route_has_no_weapons(catalog):
    # the ShieldItem route carries no category pick — the union shape makes a stray pick impossible
    choices = {"classes": [{"class": "warrior", "level": 3}],
               "equipment_0": "WeaponB", "equipment_1": {"route": "ShieldItem"}}
    inv = {i["item"]: i["quantity"] for i in equipment.assemble_inventory(catalog, choices)}
    assert inv == {"WeaponB": 1, "ShieldItem": 1}


def test_treasure_default_is_background_gold_only(catalog):
    choices = {"classes": [{"class": "warrior", "level": 3}], "background": "Scholar"}
    assert equipment.treasure(catalog, choices) == {"gp": 15}        # bg gold, no class wealth roll


def test_treasure_flag_rolls_class_wealth_plus_background(catalog):
    choices = {"classes": [{"class": "warrior", "level": 3}], "background": "Scholar",
               "roll_starting_wealth": True}
    gp = equipment.treasure(catalog, choices, random.Random(1))["gp"]
    assert 35 <= gp <= 95 and (gp - 15) % 10 == 0                    # 2d4 (2..8) x10 + 15 bg
    assert equipment.treasure(catalog, choices, random.Random(1))["gp"] == gp   # deterministic per seed


def test_roll_wealth_drops_inventory_and_armour(catalog):
    # gold instead of equipment: no class kit, unarmoured — even if equipment fields slipped through
    choices = {"classes": [{"class": "warrior", "level": 3}], "roll_starting_wealth": True,
               "equipment_0": "WeaponA", "equipment_1": {"route": "ShieldItem"}}
    assert equipment.assemble_inventory(catalog, choices) == []
    assert equipment.equipped_armour(catalog, choices) == (None, False)
