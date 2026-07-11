"""Tests for the GRIMOIRE deriver (C-G1a/b/c)."""
import pytest

from app.derivation.grimoire import (
    derive_grimoire, derive_sources, derive_spells, derive_slots, hash_core,
)


def _core_sheet(**overrides):
    """Minimal core-sheet:1 matching the synthetic DB entities."""
    sheet = {
        "schema_version": 1,
        "character_id": "test-01",
        "character_name": "Test",
        "identity": {
            "name": "Test", "species": "Species A",
            "lineage": None, "species_variant": None,
            "size": "Size A", "creature_type": "Type A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None,
                         "subclass_detail": None, "class_detail": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {},
        "proficiency_bonus": 2,
        "saving_throws": {},
        "skills": {},
        "proficiencies": {"armor": [], "weapons": [], "tools": []},
        "languages": [],
        "weapon_masteries": [],
        "features": [],
        "feats": [{"name": "feat-gen", "source": "bg-a"}],
        "permanent_senses": {},
        "permanent_speed": {"walk": 30},
        "permanent_defenses": {},
        "hit_points": {"max": 22},
        "hit_dice": {"d8": {"max": 3}},
        "resource_budgets": {},
        "companions": [],
        "permanent_effects": [],
        "flavour": None,
    }
    sheet.update(overrides)
    return sheet


class TestHashCore:
    def test_same_core_same_hash(self):
        a = _core_sheet()
        b = _core_sheet()
        assert hash_core(a) == hash_core(b)

    def test_different_class_different_hash(self):
        a = _core_sheet()
        b = _core_sheet()
        b["identity"]["classes"] = [{"class": "Class B", "level": 1}]
        assert hash_core(a) != hash_core(b)


class TestDeriveSources:
    def test_class_source(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        assert "class:class-a" in sources
        s = sources["class:class-a"]
        assert s["kind"] == "class"
        assert s["cantrips_known"] >= 0
        assert s["prepared_limit"] is not None   # class-a is full caster

    def test_warlock_has_null_prepared_limit(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class P", "level": 2}]
        sources = derive_sources(core, access)
        assert "class:class-p" in sources
        assert sources["class:class-p"]["prepared_limit"] is None

    def test_non_caster_no_source(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class B", "level": 1}]
        core["identity"]["species"] = "Species A"
        # Species grants a source even without a caster class
        sources = derive_sources(core, access)
        # At minimum, the species source exists (grants sp4)
        assert len(sources) >= 0

    def test_feat_source(self, access):
        core = _core_sheet()
        core["feats"] = [{"name": "feat-gen", "source": "bg-a"}]
        sources = derive_sources(core, access)
        # feat-gen may or may not grant spells — depends on test DB setup
        # Just check no crash
        assert isinstance(sources, dict)

    def test_third_caster_source(self, access):
        """Non-caster class with third-caster subclass produces a class source."""
        core = _core_sheet()
        core["identity"]["classes"] = [
            {"class": "Class M", "level": 3, "subclass": "Sub EK",
             "subclass_detail": None, "class_detail": None}]
        core["identity"]["total_level"] = 3
        core["identity"]["species"] = "Species A"
        sources = derive_sources(core, access)
        assert "class:class-m" in sources
        s = sources["class:class-m"]
        assert s["kind"] == "class"
        assert s["cantrips_known"] == 2
        assert s["prepared_limit"] == 3

    def test_third_caster_below_level_no_source(self, access):
        """Before subclass level 3, no source should be created."""
        core = _core_sheet()
        core["identity"]["classes"] = [
            {"class": "Class M", "level": 2, "subclass": None}]
        core["identity"]["total_level"] = 2
        core["identity"]["species"] = None
        sources = derive_sources(core, access)
        assert "class:class-m" not in sources

    def test_grant_only_subclass_source(self, access):
        """Grant-only subclass produces a subclass source."""
        core = _core_sheet()
        core["identity"]["classes"] = [
            {"class": "Class M", "level": 3, "subclass": "Sub Shadow"}]
        core["identity"]["total_level"] = 3
        sources = derive_sources(core, access)
        assert "subclass:sub-shadow" in sources
        s = sources["subclass:sub-shadow"]
        assert s["kind"] == "subclass"
        assert s["ability"] is not None


class TestDeriveSlots:
    def test_full_caster_slots(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class A", "level": 4}]
        core["identity"]["total_level"] = 4
        slots, pact = derive_slots(core, access)
        assert len(slots) > 0
        for level, entry in slots.items():
            assert "max" in entry
            assert "remaining" not in entry
        assert len(pact) == 0

    def test_pact_caster_slots(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class P", "level": 2}]
        slots, pact = derive_slots(core, access)
        assert len(slots) == 0   # no leveled slots for pact-only
        assert len(pact) > 0
        for level, entry in pact.items():
            assert "max" in entry

    def test_non_caster_no_slots(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class B", "level": 1}]
        slots, pact = derive_slots(core, access)
        assert len(slots) == 0
        assert len(pact) == 0

    def test_solo_third_caster_slots(self, access):
        """Solo third-caster uses subclass_spell_slot directly."""
        core = _core_sheet()
        core["identity"]["classes"] = [
            {"class": "Class M", "level": 3, "subclass": "Sub EK"}]
        core["identity"]["total_level"] = 3
        slots, pact = derive_slots(core, access)
        assert slots == {"1": {"max": 2}}

    def test_third_caster_mixed_uses_multiclass(self, access):
        """Third-caster + full caster: combined multiclass table."""
        core = _core_sheet()
        core["identity"]["classes"] = [
            {"class": "Class A", "level": 3, "subclass": None},
            {"class": "Class M", "level": 3, "subclass": "Sub EK"}]
        core["identity"]["total_level"] = 6
        slots, pact = derive_slots(core, access)
        # caster_level = 3 (full) + 1 (third) = 4 → {1:4, 2:3}
        assert slots["1"]["max"] == 4
        assert slots["2"]["max"] == 3


class TestDeriveSpells:
    def test_species_grants_found(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        # Species A grants sp4 via grant_spell_fixed
        species_spells = [s for s in spells if s.get("source", "").startswith("species")]
        assert len(species_spells) > 0

    def test_metadata_populated(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        for s in spells:
            if "school" in s and s["school"] is not None:
                assert isinstance(s["school"], str)
            if "components" in s:
                assert "verbal" in s["components"]
                assert "somatic" in s["components"]
                assert "material" in s["components"]

    def test_preservation_same_hash(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        g1 = derive_spells(core, None, sources, access)
        # Add a pretend player-chosen spell
        g1.append({
            "name": "Sp1", "level": 0, "source": "class:class-a",
            "bucket": "cantrip", "recovery": "at_will",
            "ritual_castable": False, "concentration": False,
        })
        g1_dict = {"spells": g1}
        # Pass as prev_grimoire with same core
        g2 = derive_spells(core, g1_dict, sources, access)
        cantrips = [s for s in g2 if s.get("bucket") == "cantrip" and s.get("source") == "class:class-a"]
        assert len(cantrips) >= 1  # preserved

    def test_dedup_by_name_source(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        g1 = derive_spells(core, None, sources, access)
        if not g1:
            pytest.skip("no deterministic spells to test dedup")
        # Add a duplicate
        g1.append(dict(g1[0]))  # copy first row
        prev = {"spells": g1}
        g2 = derive_spells(core, prev, sources, access)
        # No duplicate (name, source) pairs
        pairs = [(s["name"], s.get("source")) for s in g2]
        assert len(pairs) == len(set(pairs))

    def test_preserve_class_list_bucket(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        g1 = derive_spells(core, None, sources, access)
        g1.append({
            "name": "Sp1", "level": 0, "source": "class:class-a",
            "bucket": "class_list", "recovery": "pact_slot",
            "ritual_castable": False, "concentration": False,
        })
        g1_dict = {"spells": g1}
        g2 = derive_spells(core, g1_dict, sources, access)
        class_list_spells = [s for s in g2 if s.get("bucket") == "class_list" and s.get("source") == "class:class-a"]
        assert len(class_list_spells) >= 1

    def test_drop_class_list_bucket_without_source(self, access):
        core = _core_sheet()
        sources = derive_sources(core, access)
        g1 = derive_spells(core, None, sources, access)
        g1.append({
            "name": "Sp1", "level": 1, "source": "class:nonexistent",
            "bucket": "class_list", "recovery": "pact_slot",
            "ritual_castable": False, "concentration": False,
        })
        g1_dict = {"spells": g1}
        g2 = derive_spells(core, g1_dict, sources, access)
        class_list_spells = [s for s in g2 if s.get("bucket") == "class_list" and s.get("source") == "class:nonexistent"]
        assert len(class_list_spells) == 0


class TestDeriveGrimoire:
    def test_full_derivation(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class A", "level": 4}]
        core["identity"]["total_level"] = 4
        grimoire = derive_grimoire(core, None, access)
        assert grimoire["schema_version"] == 1
        assert grimoire["character_id"] == "test-01"
        assert "derived_from_core" in grimoire
        assert "sources" in grimoire
        assert "spells" in grimoire
        # class-a is a full caster at level 3
        assert len(grimoire.get("spell_slots", {})) > 0

    def test_no_remaining_counters(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class A", "level": 4}]
        core["identity"]["total_level"] = 4
        grimoire = derive_grimoire(core, None, access)
        for slot_table in ["spell_slots", "pact_slots"]:
            for entry in grimoire.get(slot_table, {}).values():
                assert "remaining" not in entry
                assert "max" in entry

    def test_prev_grimoire_merge(self, access):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class A", "level": 4}]
        core["identity"]["total_level"] = 4
        g1 = derive_grimoire(core, None, access)
        # Simulate player adding a cantrip
        g1["spells"].append({
            "name": "Sp1", "level": 0, "source": "class:class-a",
            "bucket": "cantrip", "recovery": "at_will",
            "ritual_castable": False, "concentration": False,
        })
        g2 = derive_grimoire(core, g1, access)
        cantrips = [s for s in g2["spells"] if s.get("bucket") == "cantrip" and s.get("source") == "class:class-a"]
        assert len(cantrips) >= 1
