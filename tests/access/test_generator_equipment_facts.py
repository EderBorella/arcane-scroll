"""Catalog-fact readers on the generator DAL (F05-T80) — the raw rows the INVENTORY assembly folds
onto an item record. Against the synthetic, content-neutral rules DB."""
from access.generator import equipment as equip


# --------------------------------------------------------------------------- base catalog facts

def test_catalog_item_facts_returns_kind_category_weight(gen_access):
    facts = equip.catalog_item_facts(gen_access, "weapon-a")
    assert facts["kind"] == "weapon"
    assert facts["weight"] == 7.0


def test_catalog_item_facts_weight_none_when_absent(gen_access):
    # a catalog item with no weight set carries weight=None (not an error)
    facts = equip.catalog_item_facts(gen_access, "weapon-b")
    assert facts["kind"] == "weapon"
    assert facts["weight"] is None


def test_catalog_item_facts_unknown_id_is_none(gen_access):
    assert equip.catalog_item_facts(gen_access, "no-such-item") is None
    assert equip.catalog_item_facts(gen_access, None) is None


# --------------------------------------------------------------------------- weapon facts

def test_weapon_facts_dice_type_mastery_properties(gen_access):
    w = equip.weapon_facts(gen_access, "weapon-a")
    assert w["dmg_dice_count"] == 1 and w["dmg_die_faces"] == 12
    assert w["damage_type_id"] == "slashing"
    assert w["mastery_id"] == "mastery-a"
    assert w["properties"] == ["two-handed"]
    assert w["range_class_id"] == "melee"


def test_weapon_facts_none_for_non_weapon(gen_access):
    # armor-e is armour, not a weapon; blade-a is a weapon catalog item with no weapon-stats row
    assert equip.weapon_facts(gen_access, "armor-e") is None
    assert equip.weapon_facts(gen_access, "blade-a") is None


# --------------------------------------------------------------------------- armour facts

def test_armor_facts_category_and_base_ac(gen_access):
    a = equip.armor_facts(gen_access, "armor-e")
    assert a["category_id"] == "light"
    assert a["base_ac"] == 11
    assert a["dex_cap"] is None


def test_armor_facts_shield_carries_ac_bonus(gen_access):
    a = equip.armor_facts(gen_access, "shield-item")
    assert a["category_id"] == "shield"
    assert a["ac_bonus"] == 2


def test_armor_facts_none_for_non_armor(gen_access):
    assert equip.armor_facts(gen_access, "weapon-a") is None
