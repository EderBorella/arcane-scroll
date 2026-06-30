"""Equipment-derived: equipped armour (for armour-based AC), inventory assembly, and treasure."""
import random

from app.derivation import equipment


def _inv(*names):
    return [{"item": n, "quantity": 1} for n in names]


def test_equipped_armour_highest_base(catalog):
    armour, shield = equipment.equipped_armour(catalog, _inv("Leather Armor", "Chain Mail", "Shield"))
    assert armour["name"] == "Chain Mail" and shield is True        # heaviest worn armour + shield


def test_equipped_armour_exact_name_no_subset(catalog):
    # exact-name match against the inventory — no "Plate Armor" ⊂ "Half Plate Armor" confusion
    assert equipment.equipped_armour(catalog, _inv("Half Plate Armor"))[0]["name"] == "Half Plate Armor"
    assert equipment.equipped_armour(catalog, _inv("Studded Leather Armor"))[0]["name"] == "Studded Leather Armor"


def test_equipped_armour_unarmoured(catalog):
    assert equipment.equipped_armour(catalog, _inv("Dagger")) == (None, False)
    assert equipment.equipped_armour(catalog, []) == (None, False)  # empty inventory (e.g. gold-instead)


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
    inv = equipment.assemble_inventory(catalog, choices)
    assert inv == []                                                # no class kit (gold instead)
    assert equipment.equipped_armour(catalog, inv) == (None, False)  # empty inventory → unarmoured
