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
    assert by_label["a martial weapon"]["pick"] == {"category": "cat-martial",
                                                    "enum": ["MartialA", "MartialB"], "n": 1}


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


def test_style_filter_keeps_route_and_filters_weapons():
    branches = [
        {"label": "weapon + shield", "pick": {"category": "martial-weapons", "enum": ["Longsword", "Greatsword"], "n": 1}},
        {"label": "two weapons", "pick": {"category": "martial-weapons", "enum": ["Longsword", "Greatsword"], "n": 2}},
    ]
    wprops = {"Greatsword": {"two-handed"}, "Longsword": set()}
    one = equipment._filter_branches(branches, {"max_weapons": 1, "exclude_props": ["two-handed"]}, wprops)
    assert [b["label"] for b in one] == ["weapon + shield"]          # 2-weapon route dropped
    assert one[0]["pick"]["enum"] == ["Longsword"]                   # two-handed weapon dropped
    two = equipment._filter_branches(branches, {"min_weapons": 2}, wprops)
    assert [b["label"] for b in two] == ["two weapons"]


def test_style_filter_falls_back_when_a_filter_would_empty(catalog):
    branches = [{"label": "two weapons", "pick": {"category": "martial-weapons", "enum": ["Greatsword"], "n": 2}}]
    wprops = {"Greatsword": {"two-handed"}}
    # dropping the only route would empty the slot → keep it
    assert equipment._filter_branches(branches, {"max_weapons": 1}, wprops)[0]["label"] == "two weapons"
    # requiring ranged would empty the enum → keep the full enum
    out = equipment._filter_branches(branches, {"require_props": ["ranged"]}, wprops)
    assert out[0]["pick"]["enum"] == ["Greatsword"]


def test_equipment_props_threads_fighting_style(catalog):
    # a style flows into equipment_props and still yields a valid union (warrior's routes both fit
    # Dueling's max_weapons=1, so this exercises threading + the no-empty fallback)
    props, _ = equipment.equipment_props(catalog, [("warrior", 3)], "Dueling")
    assert "oneOf" in props["equipment_1"] and props["equipment_1"]["oneOf"]


def test_multiclass_uses_primary_class_only(catalog):
    assert equipment.equipment_props(catalog, [("mage", 5), ("warrior", 3)]) == ({}, [])


def test_equipment_grammar_provides_slots(catalog):
    props = sheet.build_equipment_grammar(catalog, [("warrior", 3)])[0]["properties"]
    assert {"equipment_0", "equipment_1"} <= set(props) and "equipment_1_pick" not in props
    assert "oneOf" in props["equipment_1"]
