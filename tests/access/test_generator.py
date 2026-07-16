"""Access-layer tests for the generator's choice-space enumeration package (F05-T66).

Each reader is exercised against the synthetic content-neutral rules DB (the `gen_access` fixture in
tests/conftest.py). We assert: the rows/ids returned, empty/None handling for unknown owners, and the
deterministic ordering each reader promises. These are pure-read machinery tests — no rule math."""
from access.generator import backgrounds, classes, equipment, feats, species, spells


# --- species ---------------------------------------------------------------

def test_list_species(gen_access):
    rows = species.list_species(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)          # deterministic id order
    assert "species-a" in ids
    r = next(row for row in rows if row["id"] == "species-a")
    assert r["name"] == "Species A"
    assert r["creature_type_id"] == "type-a"
    assert r["base_walk_speed"] == 30


def test_species_traits_ordered_by_ordinal(gen_access):
    rows = species.species_traits(gen_access, "species-a")
    assert [r["id"] for r in rows] == ["st-a1", "st-a2"]
    assert [r["ordinal"] for r in rows] == [1, 2]


def test_species_traits_unknown_is_empty(gen_access):
    assert species.species_traits(gen_access, "nope") == []


def test_species_sizes_multi_ordered(gen_access):
    assert species.species_sizes(gen_access, "species-a") == ["size-a", "size-s"]


def test_species_sizes_unknown_is_empty(gen_access):
    assert species.species_sizes(gen_access, "nope") == []


def test_species_creature_type(gen_access):
    assert species.species_creature_type(gen_access, "species-a") == "type-a"
    assert species.species_creature_type(gen_access, "nope") is None


# --- species sub-choices (lineage / variant axis) --------------------------

def test_species_lineages_ordered_by_id(gen_access):
    rows = species.species_lineages(gen_access, "species-l")
    assert [r["id"] for r in rows] == ["lin-l1", "lin-l2"]
    assert all(r["species_id"] == "species-l" for r in rows)


def test_species_lineages_none_for_plain_species(gen_access):
    # species-a offers no lineage sub-choice
    assert species.species_lineages(gen_access, "species-a") == []
    assert species.species_lineages(gen_access, "nope") == []


def test_species_variant_options_ordered(gen_access):
    rows = species.species_variant_options(gen_access, "species-v")
    assert [r["id"] for r in rows] == ["svo-a", "svo-b"]
    assert [(r["axis"], r["option_name"], r["damage_type_id"]) for r in rows] == [
        ("axis-a", "Variant A", "fire"), ("axis-a", "Variant B", "cold")]


def test_species_variant_options_none_for_plain_species(gen_access):
    assert species.species_variant_options(gen_access, "species-a") == []
    assert species.species_variant_options(gen_access, "nope") == []


# --- classes ---------------------------------------------------------------

def test_list_classes_ordered(gen_access):
    rows = classes.list_classes(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert "class-a" in ids
    a = next(r for r in rows if r["id"] == "class-a")
    assert a["hit_die_faces"] == 8
    assert a["subclass_level"] == 3
    assert a["caster_progression"] == "full"


def test_subclasses_for_class_ordered(gen_access):
    rows = classes.subclasses_for_class(gen_access, "class-a")
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    # every returned subclass belongs to the queried class
    assert all(r["class_id"] == "class-a" for r in rows)
    assert "sub-a" in ids


def test_subclasses_for_class_unknown_is_empty(gen_access):
    assert classes.subclasses_for_class(gen_access, "nope") == []


def test_subclass_unlock_level(gen_access):
    assert classes.subclass_unlock_level(gen_access, "class-a") == 3
    assert classes.subclass_unlock_level(gen_access, "nope") is None


def test_class_skill_options_pooled(gen_access):
    choose_n, from_any, pool = classes.class_skill_options(gen_access, "class-a")
    assert choose_n == 2
    assert from_any == 0
    assert pool == ["sk1", "sk2", "sk3"]   # ordered by skill_id


def test_class_skill_options_unknown(gen_access):
    assert classes.class_skill_options(gen_access, "nope") == (None, None, [])


def test_class_primary_abilities(gen_access):
    rows = classes.class_primary_abilities(gen_access, "class-a")
    assert [(r["ability_id"], r["kind"]) for r in rows] == [("a1", "spellcasting")]


def test_class_saving_throws_ordered(gen_access):
    assert classes.class_saving_throws(gen_access, "class-a") == ["a1", "a2"]


def test_class_standard_array_ordered(gen_access):
    rows = classes.class_standard_array(gen_access, "class-a")
    assert [(r["ability_id"], r["score"]) for r in rows] == [
        ("a1", 15), ("a2", 14), ("a3", 13)]


# --- backgrounds -----------------------------------------------------------

def test_list_backgrounds_ordered(gen_access):
    rows = backgrounds.list_backgrounds(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert {"bg-a", "bg-b"} <= set(ids)


def test_background_ability_options_ordinal_order(gen_access):
    assert backgrounds.background_ability_options(gen_access, "bg-a") == ["a1", "a2", "a3"]


def test_background_skills(gen_access):
    assert backgrounds.background_skills(gen_access, "bg-a") == ["sk4"]
    assert backgrounds.background_skills(gen_access, "bg-b") == []


def test_background_origin_feat_present(gen_access):
    assert backgrounds.background_origin_feat(gen_access, "bg-a") == ("feat-origin", 0)


def test_background_origin_feat_absent(gen_access):
    # bg-b has feat_id NULL -> no origin feat; unknown id -> None
    assert backgrounds.background_origin_feat(gen_access, "bg-b") is None
    assert backgrounds.background_origin_feat(gen_access, "nope") is None


def test_background_tool(gen_access):
    # bg-a/bg-b declare no fixed tool_id column value (their tool proficiency, if any, comes via the
    # grant spine / a category choice), so the direct-column reader returns None.
    assert backgrounds.background_tool(gen_access, "bg-a") is None
    assert backgrounds.background_tool(gen_access, "nope") is None


# --- feats -----------------------------------------------------------------

def test_list_feats_all_ordered(gen_access):
    rows = feats.list_feats(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert "feat-gen" in ids


def test_list_feats_by_category(gen_access):
    rows = feats.list_feats(gen_access, category="origin")
    assert rows
    assert all(r["category"] == "origin" for r in rows)
    assert "feat-origin" in [r["id"] for r in rows]


def test_list_feats_unknown_category_is_empty(gen_access):
    assert feats.list_feats(gen_access, category="does-not-exist") == []


def test_feat_prereqs_grouped(gen_access):
    rows = feats.feat_prereqs(gen_access, "feat-pre")
    groups = [r["any_of_group"] for r in rows]
    assert groups == sorted(groups)          # ordered by any_of_group
    assert {r["kind"] for r in rows} == {"level", "ability"}


def test_feat_prereqs_none(gen_access):
    assert feats.feat_prereqs(gen_access, "feat-gen") == []


def test_ability_feat_slots_by_level(gen_access):
    # class-a opens an ability-increase/feat slot at levels 4 and 8 (the synthetic ASI spine).
    assert classes.ability_feat_slots(gen_access, "class-a", 3) == 0
    assert classes.ability_feat_slots(gen_access, "class-a", 4) == 1
    assert classes.ability_feat_slots(gen_access, "class-a", 7) == 1
    assert classes.ability_feat_slots(gen_access, "class-a", 8) == 2
    assert classes.ability_feat_slots(gen_access, "class-a", 20) == 2
    # a class with no ASI spine (class-m) opens no slots
    assert classes.ability_feat_slots(gen_access, "class-m", 20) == 0


def test_ability_increase_grant_from_any(gen_access):
    # the raw ability-score-increase feat: +2, may target any ability (from_any set, no fixed set)
    g = feats.ability_increase_grant(gen_access, "ability-score-improvement")
    assert g["points"] == 2 and g["max_per_ability"] == 2 and g["from_any"] == 1
    assert g["abilities"] == []


def test_ability_increase_grant_fixed_target(gen_access):
    # a general feat with a fixed +1 to a specific ability
    g = feats.ability_increase_grant(gen_access, "feat-inc")
    assert g["points"] == 1 and g["from_any"] == 0
    assert g["abilities"] == ["a2"]


def test_ability_increase_grant_none(gen_access):
    assert feats.ability_increase_grant(gen_access, "feat-gen") is None


# --- spells ----------------------------------------------------------------

def test_class_spell_pool_ordered_by_level_then_id(gen_access):
    rows = spells.class_spell_pool(gen_access, "class-a")
    ids = [r["id"] for r in rows]
    assert ids == ["sp1", "sp2", "sp3"]      # sp1/sp2 cantrips (0), sp3 level 1
    assert [r["level"] for r in rows] == [0, 0, 1]


def test_class_spell_pool_level_bounds(gen_access):
    cantrips = spells.class_spell_pool(gen_access, "class-a", level_min=0, level_max=0)
    assert [r["id"] for r in cantrips] == ["sp1", "sp2"]
    leveled = spells.class_spell_pool(gen_access, "class-a", level_min=1)
    assert [r["id"] for r in leveled] == ["sp3"]


def test_class_spell_pool_noncaster_or_unknown_is_empty(gen_access):
    assert spells.class_spell_pool(gen_access, "nope") == []


# --- starting equipment ----------------------------------------------------

def test_starting_equipment_options_class(gen_access):
    rows = equipment.starting_equipment_options(gen_access, "class", "class-a")
    assert [r["id"] for r in rows] == ["sa-a", "sa-b"]
    assert all(r["owner_kind"] == "class" for r in rows)


def test_starting_equipment_options_background(gen_access):
    rows = equipment.starting_equipment_options(gen_access, "background", "bg-a")
    assert [r["id"] for r in rows] == ["sa-bg"]


def test_starting_equipment_options_unknown_is_empty(gen_access):
    assert equipment.starting_equipment_options(gen_access, "class", "nope") == []


def test_starting_equipment_entries_ordered(gen_access):
    rows = equipment.starting_equipment_entries(gen_access, "sa-a")
    assert [r["sort_order"] for r in rows] == [1, 2]
    assert rows[0]["kind"] == "item"
    assert rows[0]["catalog_item_id"] == "blade-a"
    assert rows[1]["kind"] == "gp"
    assert rows[1]["gp_amount"] == 15


def test_starting_equipment_entries_tool_category_choice(gen_access):
    rows = equipment.starting_equipment_entries(gen_access, "sa-bg")
    assert len(rows) == 1
    assert rows[0]["kind"] == "tool_category_choice"
    assert rows[0]["tool_category_id"] == "tc-a"


def test_starting_equipment_entries_unknown_is_empty(gen_access):
    assert equipment.starting_equipment_entries(gen_access, "nope") == []
