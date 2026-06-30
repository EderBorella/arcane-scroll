"""Equipment-derived: detect the equipped armour (for armour-based AC) from choices + fixed package."""
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


def test_assemble_inventory_category_route_consumes_one_pick(catalog):
    # warrior slot0 = direct category (WeaponA); slot1 route "a martial weapon" consumes pick.n=1
    choices = {"classes": [{"class": "warrior", "level": 3}],
               "equipment_0": "WeaponA",
               "equipment_1": "a martial weapon", "equipment_1_pick": ["MartialA", "MartialB"]}
    inv = {i["item"]: i["quantity"] for i in equipment.assemble_inventory(catalog, choices)}
    assert inv["WeaponA"] == 1 and inv["MartialA"] == 1
    assert "MartialB" not in inv          # E1: the route needs 1 pick — the extra companion is dropped


def test_assemble_inventory_non_category_route_ignores_companion(catalog):
    # the ShieldItem route has no category pick → the companion list must not leak in
    choices = {"classes": [{"class": "warrior", "level": 3}],
               "equipment_0": "WeaponB",
               "equipment_1": "ShieldItem", "equipment_1_pick": ["MartialA"]}
    inv = {i["item"]: i["quantity"] for i in equipment.assemble_inventory(catalog, choices)}
    assert inv["ShieldItem"] == 1 and "MartialA" not in inv
