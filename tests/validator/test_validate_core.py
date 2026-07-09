"""Tests for the CORE validator — adapter + validate_core against the synthetic DB."""
import pytest
from validator.validate_core import adapt_core_to_v10, validate_core, CORE_CHECKS


class TestAdapter:
    def test_senses_remap(self):
        core = {"permanent_senses": {"darkvision": 60}}
        v10 = adapt_core_to_v10(core)
        assert "permanent_senses" not in v10
        assert v10["senses"] == {"darkvision": 60}

    def test_defenses_remap(self):
        core = {"permanent_defenses": {"resistances": ["fire"]}}
        v10 = adapt_core_to_v10(core)
        assert "permanent_defenses" not in v10
        assert v10["defenses"] == {"resistances": ["fire"]}

    def test_speed_remap(self):
        core = {"permanent_speed": {"walk": 30}}
        v10 = adapt_core_to_v10(core)
        assert "permanent_speed" not in v10
        assert v10["combat"]["speed"] == {"walk": 30}

    def test_speed_remap_when_combat_already_exists(self):
        core = {"permanent_speed": {"walk": 30}, "combat": {"armor_class": 15}}
        v10 = adapt_core_to_v10(core)
        assert "permanent_speed" not in v10
        assert v10["combat"]["speed"] == {"walk": 30}
        assert v10["combat"]["armor_class"] == 15

    def test_hit_points_remap(self):
        core = {"hit_points": {"max": 22}}
        v10 = adapt_core_to_v10(core)
        assert "hit_points" not in v10
        assert v10["combat"]["hit_points"] == {"max": 22}

    def test_hit_dice_remap(self):
        core = {"hit_dice": {"d8": {"max": 3}}}
        v10 = adapt_core_to_v10(core)
        assert "hit_dice" not in v10
        assert v10["combat"]["hit_dice"] == {"d8": {"max": 3}}

    def test_unaffected_fields_pass_through(self):
        core = {
            "character_id": "abc",
            "character_name": "Test",
            "identity": {"name": "Foo", "species": "Species A"},
            "abilities": {"str": {"final": 16}},
            "proficiency_bonus": 2,
            "features": [{"name": "test", "source": "class-a"}],
            "feats": [{"name": "feat-gen", "source": "bg-a"}],
            "permanent_senses": {"darkvision": 60},
            "permanent_speed": {"walk": 30},
            "permanent_defenses": {"resistances": []},
            "hit_points": {"max": 22},
            "hit_dice": {"d8": {"max": 3}},
        }
        v10 = adapt_core_to_v10(core)
        assert v10["character_id"] == "abc"
        assert v10["character_name"] == "Test"
        assert v10["identity"]["species"] == "Species A"
        assert v10["abilities"]["str"]["final"] == 16
        assert v10["proficiency_bonus"] == 2
        assert v10["features"][0]["name"] == "test"
        assert v10["feats"][0]["name"] == "feat-gen"

    def test_adapter_does_not_mutate_original(self):
        core = {"permanent_senses": {"darkvision": 60}}
        adapt_core_to_v10(core)
        assert "permanent_senses" in core
        assert "senses" not in core


class TestValidateCoreSmoke:
    """Smoke tests using the shared synthetic-DB fixture (built in tests/conftest.py)."""

    def _make_sheet(self, **overrides):
        """Minimal core-sheet:1 that matches the synthetic DB entities.

        The synthetic DB has: species-a (Species A), class-a (Class A, hit_die=8,
        subclass_level=3), sub-a (Sub A), bg-a (Background A), abilities a0..a5
        (abbrevs x0..x5), skills sk1..sk18, feat-gen, feat-origin, etc.
        """
        sheet = {
            "schema_version": 1,
            "character_id": "core-test-01",
            "character_name": "Test Char",
            "identity": {
                "name": "Test Char", "species": "Species A",
                "lineage": None, "species_variant": None,
                "size": "Size A", "creature_type": "Type A",
                "classes": [{"class": "Class A", "level": 1, "subclass": None,
                             "subclass_detail": None, "class_detail": None}],
                "total_level": 1, "background": "Background A",
            },
            "abilities": {},
            "proficiency_bonus": 2,
            "saving_throws": {},
            "skills": {},
            "proficiencies": {"armor": [], "weapons": [], "tools": []},
            "languages": [],
            "weapon_masteries": [],
            "features": [{"name": "cf-asi4", "source": "Class A lvl 4"}],
            "feats": [{"name": "feat-gen", "source": "bg-a"}],
            "permanent_senses": {},
            "permanent_speed": {"walk": 30},
            "permanent_defenses": {},
            "hit_points": {"max": 8},
            "hit_dice": {"d8": {"max": 1}},
            "resource_budgets": {},
            "companions": [],
            "permanent_effects": [],
            "flavour": None,
        }
        sheet.update(overrides)
        return sheet

    def test_no_internal_errors(self, access):
        sheet = self._make_sheet()
        report = validate_core(sheet, access)
        violations = report["violations"]
        internals = [x for x in violations if x["code"] == "internal"]
        assert len(internals) == 0, f"internal errors: {internals}"

    def test_all_checks_registered(self):
        assert len(CORE_CHECKS) == 12
        module_names = {c.__module__.split(".")[-1] for c in CORE_CHECKS}
        assert "spellcasting" not in module_names

    def test_unknown_species_produces_violation(self, access):
        sheet = self._make_sheet()
        sheet["identity"]["species"] = "Not A Species"
        report = validate_core(sheet, access)
        codes = {x["code"] for x in report["violations"]}
        assert "unknown-species" in codes

    def test_bad_total_level_produces_violation(self, access):
        sheet = self._make_sheet()
        sheet["identity"]["total_level"] = 99
        report = validate_core(sheet, access)
        codes = {x["code"] for x in report["violations"]}
        assert "total-level-mismatch" in codes
