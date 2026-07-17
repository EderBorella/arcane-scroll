"""Tests for the companion derivation engine + orchestrator.

Content-neutral: synthetic creatures only. creature-c is a rich CONCRETE
statblock; creature-a is a header+one-formula hybrid; creature-b is header-only;
creature-t / creature-tb are fully TEMPLATED (formula-scaled) creatures.
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

    def test_proficient_save_adds_proficiency_bonus(self, access):
        # creature-sp is proficient in a2 (pb=3): the a2 save is ability mod (+3) PLUS pb (3);
        # a1/a3 stay plain ability modifiers.
        cm = comp.derive_companion_modifier(access, 0, "creature-sp")
        saves = {s["ability"]: s["modifier"] for s in cm["saving_throws"]}
        assert saves == {"a1": -1, "a2": 6, "a3": 1}

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


class TestTemplatedDetection:
    def test_creature_with_formula_is_templated(self, access):
        assert comp.is_templated(access, "creature-a") is True
        assert comp.is_templated(access, "creature-t") is True
        assert comp.is_templated(access, "creature-tb") is True

    def test_concrete_creature_is_not_templated(self, access):
        assert comp.is_templated(access, "creature-c") is False


# ── owner CORE + GRIMOIRE builders for templated scaling ─────────────────────


def _spirit_core(cast_level=5, form="Form-Y"):
    # CORE keys abilities by SHORT code ('wis'), as real sheets do — the owner-context
    # resolver must bridge that to the DB full id ('wisdom').
    return {
        "character_id": "cid", "character_name": "Test",
        "proficiency_bonus": 3,
        "abilities": {"wis": {"final": 18}},
        "identity": {"classes": [{"class": "class-a", "level": 5}], "total_level": 5},
        "companions": [{"name": "Spirit", "db_creature_id": "creature-t",
                        "cast_level": cast_level, "form": form}],
    }


def _beast_core(level=4):
    return {
        "character_id": "cid", "character_name": "Test",
        "proficiency_bonus": 2,
        "abilities": {"wis": {"final": 16}},
        "identity": {"classes": [{"class": "class-a", "level": level, "subclass": "sub-t"}],
                     "total_level": level},
        "companions": [{"name": "Beast", "db_creature_id": "creature-tb"}],
    }


# GRIMOIRE source ability is the full DB id ('wisdom'); resolution bridges it to the
# CORE short key ('wis').
_GRIM = {"sources": {"class:class-a": {"kind": "class", "ability": "wisdom", "cantrips_known": 0}},
         "spells": []}


class TestTemplatedSpiritScaling:
    """creature-t: a spirit-like block scaled by the summoning spell level."""

    def _cm(self, access, core):
        comp_entry = core["companions"][0]
        return comp.derive_companion_modifier(access, 0, comp_entry["db_creature_id"],
                                              comp_entry, core, _GRIM)

    def test_ac_scales_with_spell_level(self, access):
        cm = self._cm(access, _spirit_core(cast_level=5))
        assert cm["armor_class"] == 15          # 10 + spell_level(5)

    def test_hp_uses_form_variant_and_above_base_threshold(self, access):
        # Form-Y hp = 30 + 5 * max(0, cast_level - 3); at 5 -> 30 + 10 = 40
        assert self._cm(access, _spirit_core(cast_level=5, form="Form-Y"))["hit_points"]["max"] == 40
        # Form-X hp base is 20 -> 20 + 10 = 30
        assert self._cm(access, _spirit_core(cast_level=5, form="Form-X"))["hit_points"]["max"] == 30

    def test_hp_above_base_floors_at_zero(self, access):
        # cast at the base level (3): no levels above base -> just the base
        assert self._cm(access, _spirit_core(cast_level=3, form="Form-Y"))["hit_points"]["max"] == 30

    def test_pb_from_owner(self, access):
        assert self._cm(access, _spirit_core())["proficiency_bonus"] == 3

    def test_attack_bonus_and_damage_scale(self, access):
        cm = self._cm(access, _spirit_core(cast_level=5))
        strike = next(a for a in cm["attacks"] if a["name"] == "Strike")
        assert strike["attack_bonus"] == 7      # spell_attack = pb(3) + wis_mod(4)
        assert strike["damage"] == "1d8 + 8"     # 3 + spell_level(5)

    def test_save_dc_scales(self, access):
        cm = self._cm(access, _spirit_core(cast_level=5))
        burst = next(a for a in cm["attacks"] if a["name"] == "Burst")
        assert burst["save_dc"] == 15            # 8 + pb(3) + wis_mod(4)

    def test_multiattack_rounds_down(self, access):
        assert self._cm(access, _spirit_core(cast_level=5))["multiattack"] == 2   # floor(5/2)
        assert self._cm(access, _spirit_core(cast_level=4))["multiattack"] == 2
        assert self._cm(access, _spirit_core(cast_level=3))["multiattack"] == 1

    def test_multiattack_action_excluded_from_attacks(self, access):
        names = {a["name"] for a in self._cm(access, _spirit_core())["attacks"]}
        assert "Multiattack" not in names

    def test_aura_save_dc_emitted_from_non_action_trait(self, access):
        # 'Aura' is a trait-kind (non-action) save-forcing ability; its scaled DC must
        # still be emitted (name + save_dc), not dropped for being a non-action.
        aura = next(a for a in self._cm(access, _spirit_core())["attacks"] if a["name"] == "Aura")
        assert aura == {"name": "Aura", "save_dc": 15}   # 8 + pb(3) + wis_mod(4)

    def test_summon_spell_source_ability_wins_over_first_source(self, access):
        # When the GRIMOIRE lists the summon spell (name == grant owner_id 'sp-t'), its
        # source's ability is used — NOT the first source (fallback). src-a is first
        # (ability 'a1', score 8 -> mod -1); the spell points at src-w (ability
        # 'wisdom', score 18 -> mod 4), which must win. CORE keys by short code.
        core = _spirit_core()
        core["abilities"] = {"wis": {"final": 18}, "x1": {"final": 8}}
        grim = {"sources": {"src-a": {"kind": "class", "ability": "a1", "cantrips_known": 0},
                            "src-w": {"kind": "class", "ability": "wisdom", "cantrips_known": 0}},
                "spells": [{"name": "sp-t", "source": "src-w"}]}
        comp_entry = core["companions"][0]
        cm = comp.derive_companion_modifier(access, 0, "creature-t", comp_entry, core, grim)
        strike = next(a for a in cm["attacks"] if a["name"] == "Strike")
        assert strike["attack_bonus"] == 7      # pb(3) + wis_mod(4); the a1 fallback would give 2
        burst = next(a for a in cm["attacks"] if a["name"] == "Burst")
        assert burst["save_dc"] == 15            # 8 + pb(3) + wis_mod(4); a1 fallback would give 10

    def test_schema_conformance(self, access):
        sheet, _ = derive_companions(_spirit_core(), None, "fill", access, _GRIM)
        assert _schema_errors(sheet) == []


class TestTemplatedBeastScaling:
    """creature-tb: a beast-like block scaled by the owner's class level + stats."""

    def _cm(self, access, core):
        comp_entry = core["companions"][0]
        return comp.derive_companion_modifier(access, 0, comp_entry["db_creature_id"],
                                              comp_entry, core, _GRIM)

    def test_hp_scales_with_owner_class_level(self, access):
        assert self._cm(access, _beast_core(level=4))["hit_points"]["max"] == 25    # 5 + 5*4
        assert self._cm(access, _beast_core(level=6))["hit_points"]["max"] == 35    # 5 + 5*6

    def test_ac_scales_with_owner_wisdom(self, access):
        assert self._cm(access, _beast_core())["armor_class"] == 16                 # 13 + wis_mod(3)

    def test_attack_scales_with_owner_stats(self, access):
        strike = next(a for a in self._cm(access, _beast_core())["attacks"] if a["name"] == "Strike B")
        assert strike["attack_bonus"] == 5        # spell_attack = pb(2) + wis_mod(3)
        assert strike["damage"] == "1d8 + 5"       # 2 + wis_mod(3)

    def test_fixed_ability_scores_and_saves_still_emitted(self, access):
        cm = self._cm(access, _beast_core())
        assert cm["ability_scores"] == {"a1": 12, "a2": 14, "a3": 10}
        saves = {s["ability"]: s["modifier"] for s in cm["saving_throws"]}
        assert saves == {"a1": 1, "a2": 2, "a3": 0}

    def test_schema_conformance(self, access):
        sheet, _ = derive_companions(_beast_core(), None, "fill", access, _GRIM)
        assert _schema_errors(sheet) == []


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

    def test_templated_hybrid_output_schema_validates(self, access):
        # creature-a: header stats + one attack_bonus formula → templated hybrid.
        core = _core(companions=[{"name": "A", "db_creature_id": "creature-a"}])
        sheet, _ = derive_companions(core, None, "fill", access)
        assert _schema_errors(sheet) == []
