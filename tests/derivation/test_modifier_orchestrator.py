"""Tests for the C-M2 MODIFIER orchestrator."""
from engine.derivation.modifier_orchestrator import derive_modifier


def _core(**overrides):
    sheet = {
        "schema_version": 1,
        "character_id": "test-01",
        "character_name": "Test",
        "identity": {
            "name": "Test", "species": "Species A",
            "size": "medium", "creature_type": "Type A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {
            "a1": {"final": 14},
            "a2": {"final": 16},
            "a3": {"final": 12},
        },
        "proficiency_bonus": 2,
        "saving_throws": {
            "a1": {"proficient": True},
            "a2": {"proficient": False},
            "a3": {"proficient": True},
        },
        "skills": {
            "sk1": {"ability": "a1", "proficient": True, "expertise": False},
            "sk2": {"ability": "a2", "proficient": False, "expertise": False},
        },
        "permanent_senses": {},
        "permanent_speed": {"walk": 30},
        "permanent_defenses": {
            "resistances": [], "immunities": [], "vulnerabilities": [],
            "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
        },
        "proficiencies": {"armor": [], "weapons": [], "tools": []},
        "weapon_masteries": [],
        "features": [{"name": "Feat A", "source": "class-a"}],
        "feats": [{"name": "feat-gen", "source": "bg-a"}],
        "resource_budgets": {},
        "hit_points": {"max": 22},
        "hit_dice": {"d8": {"max": 3}},
        "languages": [], "flavour": None,
    }
    sheet.update(overrides)
    return sheet


# ── mode A: full ─────────────────────────────────────────────────────────────


def test_full_mode_required_keys(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    required = ["schema_version", "character_id", "character_name",
                "hit_points", "death_saves", "hit_dice", "spell_slots",
                "pact_slots", "resource_state", "abilities", "saving_throws",
                "skills", "passive_scores", "effective_senses", "effective_defenses",
                "effective_size", "effective_abilities", "armor_class",
                "initiative", "speed", "character_states", "item_states",
                "features", "feats", "prepared_spells"]
    for key in required:
        assert key in sheet, f"missing {key}"


def test_full_mode_non_overwritable_defaults(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    assert sheet["xp"] == 0
    assert sheet["treasure"] == {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}
    assert sheet["hit_points"]["current"] == 22
    assert sheet["hit_points"]["temp"] == 0
    assert sheet["death_saves"] == {"successes": 0, "failures": 0}


def test_full_mode_empty_states(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    assert sheet["character_states"] == []
    assert sheet["prepared_spells"] == []


def test_full_mode_derived_fields_populated(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    assert len(sheet["abilities"]) == 3
    assert len(sheet["saving_throws"]) == 3
    assert len(sheet["skills"]) == 2
    assert sheet["armor_class"] >= 10
    assert len(sheet["speed"]) >= 1
    assert len(sheet["features"]) == 1
    assert len(sheet["feats"]) == 1


def test_full_mode_hash_fields(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    assert "derived_from_core" in sheet
    assert sheet["derived_from_grimoire"] is None
    assert isinstance(sheet["derived_from_core"], str)
    assert len(sheet["derived_from_core"]) == 16


# ── mode B: fill ────────────────────────────────────────────────────────────


def test_fill_mode_preserves_hp_current(access):
    core = _core()
    existing = {"hit_points": {"current": 10, "temp": 5, "max_boost": 0, "max_reduction": 0}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["hit_points"]["current"] == 10
    assert sheet["hit_points"]["temp"] == 5


def test_fill_mode_preserves_death_saves(access):
    core = _core()
    existing = {"death_saves": {"successes": 2, "failures": 1}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["death_saves"] == {"successes": 2, "failures": 1}


def test_fill_mode_preserves_spell_slots(access):
    core = _core()
    existing = {"spell_slots": {"1": {"remaining": 1}, "2": {"remaining": 2}}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["spell_slots"]["1"]["remaining"] == 1
    assert sheet["spell_slots"]["2"]["remaining"] == 2


def test_fill_mode_preserves_treasure(access):
    core = _core()
    existing = {"treasure": {"gp": 100, "sp": 50}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["treasure"]["gp"] == 100
    assert sheet["treasure"]["sp"] == 50
    assert sheet["treasure"]["pp"] == 0
    assert sheet["treasure"]["ep"] == 0
    assert sheet["treasure"]["cp"] == 0


def test_fill_mode_preserves_xp(access):
    core = _core()
    existing = {"xp": 5000}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["xp"] == 5000


def test_fill_mode_preserves_character_states(access):
    core = _core()
    existing = {"character_states": [{"state": "raging", "source": "rage", "source_type": "feature"}]}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert len(sheet["character_states"]) == 1
    assert sheet["character_states"][0]["state"] == "raging"


def test_fill_mode_recomputes_ac(access):
    core = _core()
    existing = {"armor_class": 99}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["armor_class"] != 99


def test_fill_mode_absent_treasure_defaults_zero(access):
    core = _core()
    existing = {"treasure": {"gp": 10}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["treasure"]["gp"] == 10
    assert sheet["treasure"]["sp"] == 0


def test_fill_mode_preserves_max_reduction_and_form_pool(access):
    """A gap-fill re-derive must not clobber a live drain max_reduction or a self-transform form-HP
    pool the caller supplied (T117). Both are live-play magnitudes once a variable-drain / transform
    state is present, so they are non-overwritable: the supplied values survive the re-derive even
    though the static build derives no such effect (base max_reduction 0; no form_temp_pool)."""
    core = _core()
    existing = {"hit_points": {"current": 22, "temp": 0, "max_boost": 0,
                               "max_reduction": 7, "form_temp_pool": 15}}
    sheet, meta = derive_modifier(core, None, None, existing, "fill", access)
    assert sheet["hit_points"]["max_reduction"] == 7
    assert sheet["hit_points"]["form_temp_pool"] == 15


# ── mode C: validate ────────────────────────────────────────────────────────


def test_validate_mode_unchanged(access):
    core = _core()
    existing = {"schema_version": 1, "xp": 9999}
    sheet, meta = derive_modifier(core, None, None, existing, "validate", access)
    assert sheet["xp"] == 9999
    assert meta["derived"] == False


def test_validate_mode_none(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "validate", access)
    assert sheet == {}
    assert meta["derived"] == False


# ── source-name dedup ────────────────────────────────────────────────────────


def test_dedup_spell_bonuses(access):
    from engine.derivation.modifier import ActiveEffects
    effects = ActiveEffects()
    effects.bonuses = [
        {"source_name": "spell-a", "target_kind": "ac", "value": 2},
        {"source_name": "spell-a", "target_kind": "ac", "value": 1},
    ]
    from engine.derivation.modifier_orchestrator import _dedup_spell_bonuses
    result = _dedup_spell_bonuses(effects)
    assert len(result.bonuses) == 1
    assert result.bonuses[0]["value"] == 2


def test_dedup_different_sources_kept(access):
    from engine.derivation.modifier import ActiveEffects
    effects = ActiveEffects()
    effects.bonuses = [
        {"source_name": "spell-a", "target_kind": "ac", "value": 2},
        {"source_name": "spell-b", "target_kind": "ac", "value": 1},
    ]
    from engine.derivation.modifier_orchestrator import _dedup_spell_bonuses
    result = _dedup_spell_bonuses(effects)
    assert len(result.bonuses) == 2


def test_prepared_spells_never_derived(access):
    core = _core()
    sheet, meta = derive_modifier(core, None, None, None, "full", access)
    assert sheet["prepared_spells"] == []


# ── effective-CON max-HP recompute (T50) ─────────────────────────────────────


def _access_with_con(access):
    """Alias a3's abbrev to 'con' in this test's private DB copy so the HP recompute resolves a3
    as the constitution ability. rules_db is rebuilt per test, so this doesn't leak."""
    import sqlite3
    from access.validator import ValidatorAccess
    con = sqlite3.connect(access.db.path)
    con.execute("UPDATE ability SET abbrev='con' WHERE id='a3'")
    con.commit()
    con.close()
    return ValidatorAccess(path=access.db.path)


def test_hp_delta_in_max_boost(access):
    access = _access_with_con(access)
    core = _core()  # a3 final=12 (mod +1), Class A level 3
    inventory = {"equipped": {"neck": {"id": "item-neck", "name": "Vigor Alpha"}}}
    existing = {"item_states": [{"inventory_ref": "item-neck", "attuned": True}]}
    sheet, meta = derive_modifier(core, inventory, None, existing, "fill", access)
    # Vigor Alpha sets con to 18 (mod +4); delta = (4 - 1) * 3 = 9
    assert sheet["hit_points"]["max_boost"] == 9
    assert sheet["hit_points"]["max_reduction"] == 0
    assert sheet["effective_abilities"]["a3"] == 18
