"""Starting-equipment choices: slot parsing (routes + category companions), props, and repair."""
from app.generation import equipment, sheet


def test_direct_category_slot(catalog):
    s0 = equipment.slots(catalog, "warrior")[0]
    assert s0["field"] == "equipment_0" and s0["enum"] == ["WeaponA", "WeaponB", "WeaponC"]
    assert s0["n"] == 1 and s0["companion"] is None


def test_alternatives_slot_gets_category_companion(catalog):
    s1 = equipment.slots(catalog, "warrior")[1]
    assert s1["enum"] == ["ShieldItem", "a martial weapon"]            # the (a)/(b) routes
    assert s1["companion"]["field"] == "equipment_1_pick"
    assert s1["companion"]["enum"] == ["MartialA", "MartialB"]         # concrete items for the category route


def test_equipment_props_shape(catalog):
    props, req = equipment.equipment_props(catalog, [("warrior", 3)])
    assert props["equipment_0"] == {"enum": ["WeaponA", "WeaponB", "WeaponC"]}
    assert props["equipment_1"] == {"enum": ["ShieldItem", "a martial weapon"]}
    assert props["equipment_1_pick"]["type"] == "array"
    assert {"equipment_0", "equipment_1", "equipment_1_pick"} <= set(req)


def test_no_slots_for_class_without_equipment(catalog):
    assert equipment.slots(catalog, "mage") == []                     # mage has no starting_equipment_options


def test_repair_fits_routes_and_allows_repeats(catalog):
    ch = {"equipment_0": "Bogus",                                     # invalid single → padded to a valid item
          "equipment_1": "a martial weapon",
          "equipment_1_pick": ["MartialA", "MartialA"]}               # companions may repeat — kept
    equipment.repair_equipment(catalog, ch, [("warrior", 3)])
    assert ch["equipment_0"] in ["WeaponA", "WeaponB", "WeaponC"]
    assert ch["equipment_1"] == "a martial weapon"
    assert ch["equipment_1_pick"] == ["MartialA"]                     # fit to n=1 (no de-dup, just truncate)


def test_repair_equipment_synthesizes_omitted_fields(catalog):
    # the model dropped every equipment field; repair must still produce valid picks
    ch = {}
    equipment.repair_equipment(catalog, ch, [("warrior", 3)])
    assert ch["equipment_0"] in ["WeaponA", "WeaponB", "WeaponC"]
    assert ch["equipment_1"] in ["ShieldItem", "a martial weapon"]
    assert ch["equipment_1_pick"] == ["MartialA"]


def test_multiclass_uses_primary_class_only(catalog):
    # primary = first class; a mage primary has no equipment slots even if warrior is second
    assert equipment.equipment_props(catalog, [("mage", 5), ("warrior", 3)]) == ({}, [])


def test_sheet_grammar_merges_equipment_fields(catalog):
    props = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])[0]["properties"]
    assert {"equipment_0", "equipment_1", "equipment_1_pick"} <= set(props)
