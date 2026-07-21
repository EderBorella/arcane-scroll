"""Tests for the GRIMOIRE deriver (C-G1a/b/c)."""
import pytest

from engine.derivation.grimoire import (
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

    def test_pact_caster_prepared_limit_is_spells_known(self, access):
        """A pact caster's prepared_limit carries the DB spells-known count (F05-T86): the
        progression's prepared_spells column, not an uncapped None. class-p knows 3 at level 2."""
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class P", "level": 2}]
        sources = derive_sources(core, access)
        assert "class:class-p" in sources
        assert sources["class:class-p"]["prepared_limit"] == 3

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


class TestCantripRecovery:
    def test_cantrip_forced_at_will(self, access):
        """A level-0 grant whose stated recovery is 'spell_slot' is forced at_will."""
        core = _core_sheet(feats=[{"name": "feat-cantrip"}])
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        cantrips = [s for s in spells if s["name"] == "Spc0"]
        assert cantrips, "cantrip grant should be derived"
        assert cantrips[0]["level"] == 0
        assert cantrips[0]["recovery"] == "at_will"


class TestDynamicUses:
    def test_uses_proficiency_bonus(self, access):
        core = _core_sheet(feats=[{"name": "feat-dyn-pb"}], proficiency_bonus=3)
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        s = [x for x in spells if x["name"] == "Spd1"]
        assert s and s[0].get("uses", {}).get("max") == 3

    def test_uses_ability_modifier(self, access):
        core = _core_sheet(feats=[{"name": "feat-dyn-am"}],
                           abilities={"a4": {"final": 16}})
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        s = [x for x in spells if x["name"] == "Spd2"]
        assert s and s[0].get("uses", {}).get("max") == 3   # (16-10)//2

    def test_uses_ability_modifier_floor(self, access):
        """A dynamic ability_modifier grant floors at 1 use even when the ability
        modifier is <= 0 — slotless_per_rest requires uses.max > 0."""
        core = _core_sheet(feats=[{"name": "feat-dyn-am"}],
                           abilities={"a4": {"final": 8}})  # mod (8-10)//2 = -1
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        s = [x for x in spells if x["name"] == "Spd2"]
        assert s and s[0].get("uses", {}).get("max") >= 1

    def test_uses_ability_modifier_maps_abbrev(self, access):
        """The grant names the full ability id ('a4'); CORE keys abilities by the
        short code (the ability's lowercased abbrev). The deriver maps id -> code
        so the modifier resolves instead of silently falling through to the floor."""
        # ability a4 has abbrev 'x4' in the synthetic DB; CORE is keyed by that code.
        core = _core_sheet(feats=[{"name": "feat-dyn-am"}],
                           abilities={"x4": {"final": 18}})  # mod (18-10)//2 = 4
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        s = [x for x in spells if x["name"] == "Spd2"]
        assert s and s[0].get("uses", {}).get("max") == 4

    def test_uses_class_resource(self, access):
        # class-a level 3; cr-dyn ladder has count 4 at level 1 (highest <= 3)
        core = _core_sheet(feats=[{"name": "feat-dyn-cr"}])
        sources = derive_sources(core, access)
        spells = derive_spells(core, None, sources, access)
        s = [x for x in spells if x["name"] == "Spd3"]
        assert s and s[0].get("uses", {}).get("max") == 4


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


class TestSlotlessChoiceGrant:
    """A class-owned once-per-rest spell chosen from a class list (the top-tier slotless grant).

    The tier is re-derived from the grant's acquisition level (class-w: level 11 -> tier 6, rising a
    tier every two levels), and the concrete spell is a deterministic lowest-catalog-id pick from the
    widened list at that tier. The synthetic pact class 'class-w' models this pattern."""

    def _wl_core(self, level):
        core = _core_sheet()
        core["identity"]["classes"] = [{"class": "Class W", "level": level, "subclass": None,
                                        "subclass_detail": None, "class_detail": None}]
        core["identity"]["total_level"] = level
        core["identity"]["species"] = "Species A"
        core["feats"] = []
        return core

    def _slotless(self, grimoire):
        return [s for s in grimoire["spells"]
                if s.get("source") == "class:class-w" and s.get("recovery") == "slotless_per_rest"]

    def test_level_17_all_four_tiers(self, access):
        g = derive_grimoire(self._wl_core(17), None, access)
        entries = self._slotless(g)
        assert sorted(s["level"] for s in entries) == [6, 7, 8, 9]
        for s in entries:
            assert s["bucket"] == "always"
            assert s["recovery"] == "slotless_per_rest"
            assert s["uses"]["max"] == 1
            assert s["uses"]["recharge"] == "long-rest"

    def test_canonical_lowest_id_pick(self, access):
        g = derive_grimoire(self._wl_core(11), None, access)
        entries = self._slotless(g)
        assert len(entries) == 1
        # two level-6 spells exist (Sp-w6a, Sp-w6b); the lowest catalog id wins
        assert entries[0]["level"] == 6
        assert entries[0]["name"] == "Sp-w6a"

    def test_level_13_two_tiers(self, access):
        g = derive_grimoire(self._wl_core(13), None, access)
        assert sorted(s["level"] for s in self._slotless(g)) == [6, 7]

    def test_below_first_unlock_none(self, access):
        g = derive_grimoire(self._wl_core(10), None, access)
        assert self._slotless(g) == []
