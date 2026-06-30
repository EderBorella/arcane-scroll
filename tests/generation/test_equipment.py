"""Starting-equipment choices: slot specs, schema props (incl. the discriminated-union route), repair."""
from app.generation import equipment, sheet


def test_direct_category_slot(catalog):
    s0 = equipment.slots(catalog, "warrior")[0]
    assert s0["field"] == "equipment_0" and s0["kind"] == "category"
    assert s0["enum"] == ["WeaponA", "WeaponB", "WeaponC"] and s0["n"] == 1


def test_route_slot_is_a_union_with_per_branch_picks(catalog):
    s1 = equipment.slots(catalog, "warrior")[1]
    assert s1["field"] == "equipment_1" and s1["kind"] == "union"
    by_label = {b["label"]: b for b in s1["branches"]}
    assert by_label["ShieldItem"]["pick"] is None                       # concrete route — no picks
    assert by_label["a martial weapon"]["pick"] == {"enum": ["MartialA", "MartialB"], "n": 1}


def test_equipment_props_shape(catalog):
    props, req = equipment.equipment_props(catalog, [("warrior", 3)])
    assert props["equipment_0"] == {"enum": ["WeaponA", "WeaponB", "WeaponC"]}
    # the category route is a discriminated union: each branch's weapons array is sized to that route
    branches = {b["properties"]["route"]["const"]: b for b in props["equipment_1"]["oneOf"]}
    assert "weapons" not in branches["ShieldItem"]["properties"]
    w = branches["a martial weapon"]["properties"]["weapons"]
    assert w["minItems"] == w["maxItems"] == 1 and w["items"]["enum"] == ["MartialA", "MartialB"]
    assert set(req) == {"equipment_0", "equipment_1"}                   # no separate _pick field anymore


def test_no_slots_for_class_without_equipment(catalog):
    assert equipment.slots(catalog, "mage") == []


def test_repair_fits_union_route_and_weapon_count(catalog):
    # off-enum weapon + an extra pick the route can't hold → fit to the chosen route's exact count
    ch = {"equipment_0": "Bogus",
          "equipment_1": {"route": "a martial weapon", "weapons": ["Bogus", "MartialB"]}}
    equipment.repair_equipment(catalog, ch, [("warrior", 3)])
    assert ch["equipment_0"] in ["WeaponA", "WeaponB", "WeaponC"]
    assert ch["equipment_1"]["route"] == "a martial weapon"
    assert ch["equipment_1"]["weapons"] == ["MartialB"]                 # fit to n=1, off-enum dropped


def test_repair_concrete_route_carries_no_weapons(catalog):
    ch = {"equipment_1": {"route": "ShieldItem", "weapons": ["MartialA"]}}   # ShieldItem takes no pick
    equipment.repair_equipment(catalog, ch, [("warrior", 3)])
    assert ch["equipment_1"] == {"route": "ShieldItem"}                 # stray weapons dropped


def test_repair_equipment_synthesizes_omitted_fields(catalog):
    ch = {}                                                             # model dropped every field
    equipment.repair_equipment(catalog, ch, [("warrior", 3)])
    assert ch["equipment_0"] in ["WeaponA", "WeaponB", "WeaponC"]
    assert ch["equipment_1"]["route"] in ["ShieldItem", "a martial weapon"]


def test_multiclass_uses_primary_class_only(catalog):
    assert equipment.equipment_props(catalog, [("mage", 5), ("warrior", 3)]) == ({}, [])


def test_sheet_grammar_merges_equipment_fields(catalog):
    props = sheet.build_grammar(catalog, "Human", [("warrior", 3)], ["Champion"])[0]["properties"]
    assert {"equipment_0", "equipment_1"} <= set(props) and "equipment_1_pick" not in props
    assert "oneOf" in props["equipment_1"]
