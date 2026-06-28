"""Feature-choice registry: count progressions, per-subclass gating, feats/ASI, race options,
grammar prop shapes, and repair."""
from app.generation import features, sheet


def _by_field(ds):
    return {d["field"]: d for d in ds}


# ── count progressions (pure) ─────────────────────────────────────────────────
def test_count_progressions():
    assert (features._maneuvers_n(3), features._maneuvers_n(7), features._maneuvers_n(15)) == (3, 5, 9)
    assert (features._invocations_n(1), features._invocations_n(2), features._invocations_n(9)) == (0, 2, 5)
    assert (features._metamagic_n(3), features._metamagic_n(10), features._metamagic_n(17)) == (2, 3, 4)
    assert (features._third_cantrips_n(3), features._third_cantrips_n(10)) == (2, 3)
    assert (features._third_max_spell_lv(3), features._third_max_spell_lv(13)) == (1, 3)


# ── fighting style + expertise ────────────────────────────────────────────────
def test_fighting_style_descriptor(catalog):
    fs = _by_field(features.descriptors(catalog, [("fighter", 1, None)]))["fighting_style"]
    assert fs["enum"] == ["StyleA", "StyleB", "StyleC"] and fs["n"] == 1


def test_expertise_scales_with_level(catalog):
    n1 = _by_field(features.descriptors(catalog, [("rogue", 1, None)]))["expertise"]["n"]
    n6 = _by_field(features.descriptors(catalog, [("rogue", 6, None)]))["expertise"]["n"]
    assert (n1, n6) == (2, 4)
    assert _by_field(features.descriptors(catalog, [("rogue", 1, None)]))["expertise"]["enum"] == \
        ["Brawn", "Focus", "Menace", "Watch"]


def test_low_level_plain_caster_has_no_features(catalog):
    assert features.descriptors(catalog, [("mage", 3, "Evoker")]) == []   # no style/expertise/oddity/ASI yet


# ── subclass feature oddities ─────────────────────────────────────────────────
def test_sorcerer_metamagic_and_ancestry(catalog):
    ds = _by_field(features.descriptors(catalog, [("sorcerer", 3, "Draconic Bloodline")]))
    assert ds["metamagic"]["n"] == 2 and ds["metamagic"]["enum"] == ["MetaA", "MetaB", "MetaC"]
    assert ds["draconic_ancestry"]["n"] == 1                              # single pick
    assert _by_field(features.descriptors(catalog, [("sorcerer", 10, "Wild Magic")])).get("draconic_ancestry") is None


def test_warlock_pact_and_invocations(catalog):
    ds = _by_field(features.descriptors(catalog, [("warlock", 5, "Fiend")]))
    assert ds["pact_boon"]["n"] == 1
    assert ds["invocations"]["n"] == 3                                    # _invocations_n(5)


def test_battlemaster_maneuvers_and_ranger_picks(catalog):
    assert _by_field(features.descriptors(catalog, [("fighter", 3, "Battle Master")]))["maneuvers"]["n"] == 3
    ranger = _by_field(features.descriptors(catalog, [("ranger", 1, None)]))
    assert ranger["favored_enemy"]["n"] == 1 and ranger["favored_terrain"]["n"] == 1


def test_barbarian_totems_unlock_by_level(catalog):
    ds = _by_field(features.descriptors(catalog, [("barbarian", 6, "Totem Warrior")]))
    assert "totem_spirit" in ds and "totem_aspect" in ds and "totem_attunement" not in ds   # @14


def test_eldritch_knight_spells_are_school_filtered(catalog):
    ds = _by_field(features.descriptors(catalog, [("fighter", 3, "Eldritch Knight")]))
    assert ds["ek_cantrips"]["enum"] == ["Wiz Cantrip A", "Wiz Cantrip B"]
    assert ds["ek_spells"]["enum"] == ["Evoke Bolt", "Ward Sigil"]        # only abjuration/evocation, not illusion


# ── feats / ASI ───────────────────────────────────────────────────────────────
def test_single_feat_slot_offers_an_asi_alternative(catalog):
    feat = _by_field(features.descriptors(catalog, [("fighter", 4, None)]))["feat"]
    assert feat["n"] == 1 and any(o.startswith("Ability Score Improvement") for o in feat["enum"])


def test_multiple_feat_slots_reserve_one_for_a_code_asi(catalog):
    feat = _by_field(features.descriptors(catalog, [("fighter", 8, None)]))["feat"]   # 3 slots @4,6,8
    assert feat["n"] == 2 and not any(o.startswith("Ability Score Improvement") for o in feat["enum"])


# ── race-level choices ────────────────────────────────────────────────────────
def test_race_choices(catalog):
    assert "dragonborn_ancestry" in _by_field(features.descriptors(catalog, [("fighter", 1, None)], "Dragonborn"))
    assert "high_elf_cantrip" in _by_field(features.descriptors(catalog, [("mage", 1, None)], "High Elf"))
    hs = _by_field(features.descriptors(catalog, [("mage", 1, None)], "Half-Elf"))["half_elf_skills"]
    assert hs["n"] == 2


# ── grammar props + repair ────────────────────────────────────────────────────
def test_feature_props_single_is_string_multi_is_array(catalog):
    props, req = features.feature_props(catalog, [("sorcerer", 3, "Draconic Bloodline")])
    assert props["draconic_ancestry"] == {"enum": ["DracA", "DracB"]}     # n==1 → bare enum
    assert props["metamagic"]["type"] == "array" and props["metamagic"]["minItems"] == 2
    assert {"metamagic", "draconic_ancestry"} <= set(req)


def test_repair_single_pick_drops_invalid_to_string(catalog):
    ch = {"draconic_ancestry": "Bogus"}
    features.repair_features(catalog, ch, [("sorcerer", 3, "Draconic Bloodline")])
    assert ch["draconic_ancestry"] in ("DracA", "DracB")                  # padded to a valid string


def test_repair_multi_dedups_and_fits(catalog):
    ch = {"metamagic": ["MetaA", "MetaA", "Bogus"]}
    features.repair_features(catalog, ch, [("sorcerer", 3, "Draconic Bloodline")])
    assert len(ch["metamagic"]) == 2 == len(set(ch["metamagic"]))


def test_repair_expertise_is_subset_of_chosen_skills(catalog):
    ch = {"skill_choices": ["Brawn", "Menace", "Watch", "Focus"], "expertise": ["Brawn", "Bogus", "Brawn"]}
    features.repair_features(catalog, ch, [("rogue", 1, None)])
    assert len(ch["expertise"]) == 2 == len(set(ch["expertise"]))
    assert set(ch["expertise"]) <= set(ch["skill_choices"])


# ── sheet integration ─────────────────────────────────────────────────────────
def test_sheet_grammar_merges_feature_fields(catalog):
    fighter_props = sheet.build_grammar(catalog, "Human", [("fighter", 1)], [None])[0]["properties"]
    assert "fighting_style" in fighter_props
    rogue_props = sheet.build_grammar(catalog, "Human", [("rogue", 1)], [None])[0]["properties"]
    assert "expertise" in rogue_props and "fighting_style" not in rogue_props
