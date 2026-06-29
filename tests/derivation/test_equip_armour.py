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


def test_unarmoured_returns_none(catalog):
    armour, shield = equipment.equipped_armour(catalog, {
        "classes": [{"class": "Mage", "level": 5}], "equipment_0": "Dagger", "equipment_1": "arcane focus"})
    assert armour is None and shield is False
