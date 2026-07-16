"""Tests for the concrete-companion derivation engine + orchestrator.

Content-neutral: synthetic creatures only. creature-c is a rich CONCRETE
statblock; creature-a carries a creature_formula row (templated → stubbed);
creature-b is header-only.
"""
import json
import pathlib

from jsonschema import Draft202012Validator

from app.derivation import companion as comp
from app.derivation.companion_orchestrator import derive_companions

_SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[2] / "contracts" / "companion-modifier.schema.json").read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


def _schema_errors(sheet) -> list:
    return sorted(f"{list(e.path)}: {e.message}" for e in _VALIDATOR.iter_errors(sheet))


def _core(companions=None):
    return {
        "character_id": "cid",
        "character_name": "Test",
        "companions": companions if companions is not None else [
            {"name": "Companion C", "db_creature_id": "creature-c"},
        ],
    }


class TestConcreteDerivation:
    def test_full_statblock_fields(self, access):
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        assert cm["companion_index"] == 0
        assert cm["ability_scores"] == {"a1": 8, "a2": 16, "a3": 12}
        assert cm["armor_class"] == 12
        assert cm["hit_points"] == {"max": 7, "current": 7, "temp": 0}
        assert cm["hit_dice"] == {"d6": {"max": 2, "remaining": 2}}
        assert cm["speed"] == {"walk": 30, "fly": 40, "swim": 30}
        assert cm["senses"] == {"darkvision": 90}
        assert cm["passive_perception"] == 13
        assert cm["character_states"] == []

    def test_skills_from_catalog(self, access):
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        assert cm["skills"] == [{"name": "sk1", "bonus": 4}, {"name": "sk2", "bonus": 2}]

    def test_saves_are_ability_mods(self, access):
        # No creature save-proficiency data → each save equals its ability modifier.
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        saves = {s["ability"]: s["modifier"] for s in cm["saving_throws"]}
        assert saves == {"a1": -1, "a2": 3, "a3": 1}

    def test_attacks_only_include_actions_with_atk_bonus(self, access):
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        # 'Recharge Move' has no atk_bonus → excluded; 'Trait C' is a trait → excluded.
        assert cm["attacks"] == [
            {"name": "Bite", "attack_bonus": 5, "damage": "1d6 + 3", "damage_type": "fire"},
        ]

    def test_defenses_split_by_kind(self, access):
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        assert cm["defenses"] == {
            "resistance": ["fire"],
            "immunity": {"damage": ["poison"], "condition": ["poisoned"]},
            "vulnerability": ["cold"],
        }

    def test_speed_and_hp_always_present(self, access):
        cm = comp.derive_companion_modifier(access, 0, "creature-c")
        assert cm["speed"] and "hit_points" in cm


class TestTemplatedStub:
    def test_templated_creature_is_stubbed(self, access):
        # creature-a has a creature_formula row → templated → minimal stub only.
        assert comp.is_templated(access, "creature-a") is True
        cm = comp.derive_companion_modifier(access, 0, "creature-a")
        assert set(cm) == {"companion_index", "hit_points", "speed"}
        assert cm["hit_points"]["max"] == 10   # from header hp_average, no formula eval
        assert cm["speed"]  # at least one mode

    def test_concrete_creature_is_not_templated(self, access):
        assert comp.is_templated(access, "creature-c") is False


class TestEmptyCreature:
    def test_header_only_creature_derives_minimal_but_valid(self, access):
        # creature-b: no child rows → falls back to a walk-speed floor, empty stats.
        cm = comp.derive_companion_modifier(access, 0, "creature-b")
        assert cm["speed"] == {"walk": 0}
        assert cm["hit_points"] == {"max": 0, "current": 0, "temp": 0}
        assert "hit_dice" not in cm            # no hp_dice → key omitted
        assert "armor_class" not in cm         # no ac_value → key omitted

    def test_empty_ability_scores_key_is_omitted(self, access):
        # ability_scores is contract minProperties:1 WHEN present — a creature with no
        # ability rows must omit the key, not emit {} (which would fail schema validation).
        cm = comp.derive_companion_modifier(access, 0, "creature-b")
        assert "ability_scores" not in cm


class TestOrchestrator:
    def test_fill_from_scratch(self, access):
        sheet, meta = derive_companions(_core(), None, "fill", access)
        assert meta == {"mode": "fill", "derived": True}
        assert sheet["schema_version"] == 1
        assert sheet["character_id"] == "cid"
        assert len(sheet["companion_modifiers"]) == 1
        assert sheet["companion_modifiers"][0]["companion_index"] == 0

    def test_validate_mode_echoes_existing(self, access):
        existing = {"schema_version": 1, "companion_modifiers": []}
        sheet, meta = derive_companions(_core(), existing, "validate", access)
        assert meta["derived"] is False
        assert sheet == existing

    def test_fill_gaps_preserves_session_state(self, access):
        # Existing sheet carries live session values that a re-derive must NOT clobber.
        existing = {
            "schema_version": 1, "character_id": "cid", "character_name": "Test",
            "companion_modifiers": [{
                "companion_index": 0,
                "hit_points": {"max": 7, "current": 2, "temp": 5},
                "hit_dice": {"d6": {"max": 2, "remaining": 0}},
                "character_states": [
                    {"state": "poisoned", "source": "x", "source_type": "condition"}],
            }],
        }
        sheet, _ = derive_companions(_core(), existing, "fill", access)
        cm = sheet["companion_modifiers"][0]
        # non-overwritable session fields preserved from the existing sheet
        assert cm["hit_points"]["current"] == 2
        assert cm["hit_points"]["temp"] == 5
        assert cm["hit_dice"]["d6"]["remaining"] == 0
        assert cm["character_states"] == [
            {"state": "poisoned", "source": "x", "source_type": "condition"}]
        # derived (overwritable) facts still refreshed
        assert cm["hit_points"]["max"] == 7
        assert cm["ability_scores"] == {"a1": 8, "a2": 16, "a3": 12}

    def test_skips_companion_with_no_creature_id(self, access):
        core = _core(companions=[{"name": "No id"}])
        sheet, _ = derive_companions(core, None, "fill", access)
        assert sheet["companion_modifiers"] == []

    def test_indexes_track_core_order(self, access):
        core = _core(companions=[
            {"name": "C", "db_creature_id": "creature-c"},
            {"name": "B", "db_creature_id": "creature-b"},
        ])
        sheet, _ = derive_companions(core, None, "fill", access)
        indexes = [cm["companion_index"] for cm in sheet["companion_modifiers"]]
        assert indexes == [0, 1]


class TestSchemaConformance:
    def test_concrete_output_schema_validates(self, access):
        sheet, _ = derive_companions(_core(), None, "fill", access)
        assert _schema_errors(sheet) == []

    def test_empty_creature_output_schema_validates(self, access):
        # creature-b: no ability rows → ability_scores omitted (not {}), so the
        # minProperties:1 constraint is not violated.
        core = _core(companions=[{"name": "B", "db_creature_id": "creature-b"}])
        sheet, _ = derive_companions(core, None, "fill", access)
        assert _schema_errors(sheet) == []

    def test_templated_stub_output_schema_validates(self, access):
        core = _core(companions=[{"name": "A", "db_creature_id": "creature-a"}])
        sheet, _ = derive_companions(core, None, "fill", access)
        assert _schema_errors(sheet) == []
