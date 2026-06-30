"""Starting-equipment choices: slot specs, schema props (incl. the discriminated-union route), repair."""
from app.generation import equipment, sheet


def test_direct_category_slot(catalog):
    s0 = equipment.slots(catalog, "warrior")[0]
    assert s0["field"] == "equipment_0" and s0["kind"] == "category"
    assert s0["enum"] == ["WeaponA", "WeaponB", "WeaponC"] and s0["n"] == 1


def test_route_slot_is_a_union_with_alternatives(catalog):
    s1 = equipment.slots(catalog, "warrior")[1]
    assert s1["field"] == "equipment_1" and s1["kind"] == "union"
    by_label = {a["label"]: a for a in s1["alternatives"]}
    assert by_label["ShieldItem"]["pick"] is None                       # concrete route — no picks
    assert by_label["ShieldItem"]["items"] == [{"item": "ShieldItem", "qty": 1}]   # routes carry items now
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


def _alts():   # two category-pick routes: one-weapon and two-weapon
    return [
        {"label": "weapon + shield", "items": [], "pick": {"category": "mw", "enum": ["Longsword", "Greatsword"], "n": 1}},
        {"label": "two weapons", "items": [], "pick": {"category": "mw", "enum": ["Longsword", "Greatsword"], "n": 2}},
    ]


_WP = {"Greatsword": {"two-handed"}, "Longsword": set(), "Shortbow": {"ranged"}, "Shortsword": set()}


def test_constrain_union_keeps_route_and_filters_pick():
    one = equipment._constrain(_alts(), {"max_weapons": 1, "exclude_props": ["two-handed"]}, _WP, set())
    assert [a["label"] for a in one] == ["weapon + shield"]          # 2-weapon route dropped
    assert one[0]["pick"]["enum"] == ["Longsword"]                   # two-handed weapon dropped
    two = equipment._constrain(_alts(), {"min_weapons": 2}, _WP, set())
    assert [a["label"] for a in two] == ["two weapons"]


def test_constrain_filters_concrete_routes_by_property():
    # the rogue/ranger fix: a melee style drops a concrete route that grants a ranged weapon
    alts = [{"label": "Shortsword", "items": [{"item": "Shortsword", "qty": 1}], "pick": None},
            {"label": "Shortbow", "items": [{"item": "Shortbow", "qty": 1}], "pick": None}]
    out = equipment._constrain(alts, {"exclude_props": ["ranged"]}, _WP, set())
    assert [a["label"] for a in out] == ["Shortsword"]


def test_constrain_min_weapons_keeps_concrete_single_weapon_routes():
    # a two-weapon style must NOT drop a single-weapon concrete route (the char gets its 2nd weapon
    # from another slot) — only the ranged route is dropped here
    alts = [{"label": "Shortsword", "items": [{"item": "Shortsword", "qty": 1}], "pick": None},
            {"label": "Shortbow", "items": [{"item": "Shortbow", "qty": 1}], "pick": None}]
    out = equipment._constrain(alts, {"min_weapons": 2, "exclude_props": ["ranged"]}, _WP, set())
    assert [a["label"] for a in out] == ["Shortsword"]


def test_constrain_shield_route_excludes_two_handed_even_without_style():
    # the shield rule applies regardless of fighting style
    alts = [{"label": "weapon + shield", "items": [{"item": "Shield", "qty": 1}],
             "pick": {"category": "mw", "enum": ["Longsword", "Greatsword"], "n": 1}}]
    out = equipment._constrain(alts, {}, _WP, {"Shield"})
    assert out[0]["pick"]["enum"] == ["Longsword"]                   # greatsword dropped — can't pair with a shield


def test_constrain_falls_back_when_a_filter_would_empty():
    alts = [{"label": "two weapons", "items": [], "pick": {"category": "mw", "enum": ["Greatsword"], "n": 2}}]
    # dropping the only route would empty the slot → keep it
    assert [a["label"] for a in equipment._constrain(alts, {"max_weapons": 1}, _WP, set())] == ["two weapons"]
    # requiring ranged would empty the enum → keep the full enum
    assert equipment._constrain(alts, {"require_props": ["ranged"]}, _WP, set())[0]["pick"]["enum"] == ["Greatsword"]


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
