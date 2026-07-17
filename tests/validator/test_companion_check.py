"""Tests for the COMPANION validator.

Content-neutral: synthetic creatures only (creature-c a rich concrete statblock;
creature-t / creature-tb fully templated/formula-scaled). The check re-derives
each value from the creature catalog + owner context independently of any deriver
output.
"""
from app.derivation.companion_orchestrator import derive_companions
from validator.checks.companion import check


def _core(**overrides):
    core = {
        "character_id": "cid",
        "character_name": "Test",
        "companions": [
            {"name": "Companion C", "db_creature_id": "creature-c"},
        ],
    }
    core.update(overrides)
    return core


def _clean_concrete_modifier(index=0):
    """A hand-built companionModifier that matches creature-c exactly — built from the
    rule/catalog facts, not from the deriver's output."""
    return {
        "companion_index": index,
        "ability_scores": {"a1": 8, "a2": 16, "a3": 12},
        "armor_class": 12,
        "hit_points": {"max": 7, "current": 7, "temp": 0},
        "hit_dice": {"d6": {"max": 2, "remaining": 2}},
        "speed": {"walk": 30, "fly": 40, "swim": 30},
        "senses": {"darkvision": 90},
        "skills": [{"name": "sk1", "bonus": 4}, {"name": "sk2", "bonus": 2}],
        "saving_throws": [
            {"ability": "a1", "modifier": -1},
            {"ability": "a2", "modifier": 3},
            {"ability": "a3", "modifier": 1},
        ],
        "passive_perception": 13,
        "attacks": [
            {"name": "Bite", "attack_bonus": 5, "damage": "1d6 + 3", "damage_type": "fire"},
        ],
        "defenses": {
            "resistance": ["fire"],
            "immunity": {"damage": ["poison"], "condition": ["poisoned"]},
            "vulnerability": ["cold"],
        },
        "character_states": [],
    }


def _sheet(companion_modifiers, core=None):
    return {"core": core or _core(),
            "companion": {"schema_version": 1, "character_id": "cid",
                          "character_name": "Test",
                          "companion_modifiers": companion_modifiers}}


# ── save proficiency (T63): pb folds into a proficient save ───────────────────


def _sp_core():
    return {"character_id": "cid", "character_name": "Test",
            "companions": [{"name": "Companion SP", "db_creature_id": "creature-sp"}]}


def _clean_sp_modifier(index=0):
    """A hand-built companionModifier matching creature-sp (pb=3, a2 proficient) — the a2
    save carries ability mod (+3) PLUS pb (3); a1/a3 are plain ability mods."""
    return {
        "companion_index": index,
        "ability_scores": {"a1": 8, "a2": 16, "a3": 12},
        "armor_class": 13,
        "hit_points": {"max": 9, "current": 9, "temp": 0},
        "hit_dice": {"d8": {"max": 2, "remaining": 2}},
        "speed": {"walk": 30},
        "saving_throws": [
            {"ability": "a1", "modifier": -1},
            {"ability": "a2", "modifier": 6},
            {"ability": "a3", "modifier": 1},
        ],
        "character_states": [],
    }


class TestSaveProficiency:
    def test_clean_proficient_save_passes(self, access):
        cm = _clean_sp_modifier()
        violations = check(_sheet([cm], core=_sp_core()), access)
        assert not any(v.code.startswith("companion-save") for v in violations)

    def test_derived_proficient_save_round_trips_clean(self, access):
        companion, _ = derive_companions(_sp_core(), None, "fill", access)
        violations = check({"core": _sp_core(), "companion": companion}, access)
        assert not any(v.code.startswith("companion-save") for v in violations)

    def test_proficient_save_without_pb_fires_mismatch(self, access):
        # A proficient save carrying only the ability modifier (pb omitted) is a mismatch.
        gap = _clean_sp_modifier()
        gap["saving_throws"][1]["modifier"] = 3          # a2 without pb
        codes = {v.code for v in check(_sheet([gap], core=_sp_core()), access)}
        assert "companion-save-mismatch" in codes

    def test_missing_proficient_save_fires_incomplete(self, access):
        gap = _clean_sp_modifier()
        gap["saving_throws"] = [{"ability": "a1", "modifier": -1}]   # drop a2/a3
        codes = {v.code for v in check(_sheet([gap], core=_sp_core()), access)}
        assert "companion-save-missing" in codes


# ── T61: creature-legality gate (independent, re-derived from grant links) ────


class TestCreatureLegalityGate:
    def test_granted_creature_is_legal(self, access):
        # creature-c is conferred by a grant_companion link → no legality violation.
        violations = check(_sheet([_clean_concrete_modifier()]), access)
        assert not any(v.code.startswith("companion-creature-illegal")
                       or v.code == "companion-creature-level-illegal" for v in violations)

    def test_ungranted_creature_is_illegal(self, access):
        # creature-form exists in the catalog but NO grant_companion link confers it
        # as a companion → it is not a rules-legal companion choice.
        core = _core(companions=[{"name": "Form", "db_creature_id": "creature-form"}])
        cm = _clean_concrete_modifier()
        codes = {v.code for v in check(_sheet([cm], core=core), access)}
        assert "companion-creature-illegal" in codes

    def test_illegal_creature_finding_is_illegal_kind(self, access):
        core = _core(companions=[{"name": "Form", "db_creature_id": "creature-form"}])
        v = next(x for x in check(_sheet([_clean_concrete_modifier()], core=core), access)
                 if x.code == "companion-creature-illegal")
        assert v.kind == "illegal"

    def test_spell_cast_below_summon_level_is_level_illegal(self, access):
        # creature-t is granted at spell level 3; a cast level below that cannot field it.
        cm = _clean_spirit_modifier()
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core(cast_level=2)), access)}
        assert "companion-creature-level-illegal" in codes

    def test_spell_cast_at_or_above_summon_level_is_legal(self, access):
        cm = _clean_spirit_modifier()
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core(cast_level=5)), access)}
        assert "companion-creature-level-illegal" not in codes

    def test_subclass_companion_below_feature_level_is_level_illegal(self, access):
        # creature-tb is a subclass companion gained at level 3; an owner below that
        # cannot yet field it.
        cm = _clean_beast_modifier()
        codes = {v.code for v in check(_templated_sheet(cm, _beast_core(level=2)), access)}
        assert "companion-creature-level-illegal" in codes

    def test_concrete_companion_without_cast_level_not_level_flagged(self, access):
        # A concrete companion (creature-c) carries no cast_level; the spell-tier gate
        # must not false-flag it.
        codes = {v.code for v in check(_sheet([_clean_concrete_modifier()]), access)}
        assert "companion-creature-level-illegal" not in codes


# ── RED: the check fires on a crafted gap sheet ──────────────────────────────


class TestGapSheetFires:
    def test_wrong_hp_and_missing_attack_fire(self, access):
        gap = _clean_concrete_modifier()
        gap["hit_points"]["max"] = 99          # wrong HP
        gap["attacks"] = []                    # missing the catalogued Bite attack
        violations = check(_sheet([gap]), access)
        codes = {v.code for v in violations}
        assert "companion-hp-mismatch" in codes
        assert "companion-attack-missing" in codes

    def test_wrong_speed_fires(self, access):
        gap = _clean_concrete_modifier()
        gap["speed"] = {"walk": 99}
        violations = check(_sheet([gap]), access)
        assert any(v.code == "companion-speed-mismatch" for v in violations)

    def test_wrong_ability_and_save_fire(self, access):
        gap = _clean_concrete_modifier()
        gap["ability_scores"]["a2"] = 20
        gap["saving_throws"][1]["modifier"] = 9
        violations = check(_sheet([gap]), access)
        codes = {v.code for v in violations}
        assert "companion-abilities-mismatch" in codes
        assert "companion-save-mismatch" in codes

    def test_missing_defense_fires(self, access):
        gap = _clean_concrete_modifier()
        gap["defenses"]["resistance"] = []     # drop the catalogued fire resistance
        violations = check(_sheet([gap]), access)
        assert any(v.code == "companion-defense-subset-violation" for v in violations)

    def test_out_of_range_index_fires(self, access):
        cm = _clean_concrete_modifier(index=5)
        violations = check(_sheet([cm]), access)
        assert any(v.code == "companion-index-out-of-range" for v in violations)

    def test_unknown_creature_fires(self, access):
        core = _core(companions=[{"name": "X", "db_creature_id": "no-such-creature"}])
        cm = _clean_concrete_modifier()
        violations = check(_sheet([cm], core=core), access)
        assert any(v.code == "companion-creature-unknown" for v in violations)

    def test_wrong_hit_dice_max_fires(self, access):
        gap = _clean_concrete_modifier()
        gap["hit_dice"] = {"d6": {"max": 5, "remaining": 5}}   # creature-c is 2d6
        violations = check(_sheet([gap]), access)
        assert any(v.code == "companion-hit-dice-mismatch" for v in violations)


# ── RED: catalog-has-it AND sheet-omits-it must be flagged (incomplete) ───────


class TestOmittedCatalogFieldFires:
    def test_omitted_ability_scores_fires(self, access):
        gap = _clean_concrete_modifier()
        del gap["ability_scores"]
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-abilities-missing" in codes

    def test_omitted_saving_throws_fires(self, access):
        gap = _clean_concrete_modifier()
        gap["saving_throws"] = []              # creature-c has abilities → saves expected
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-save-missing" in codes

    def test_omitted_skills_fires(self, access):
        gap = _clean_concrete_modifier()
        del gap["skills"]                      # creature-c has catalogued skills
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-skills-missing" in codes

    def test_omitted_ac_fires(self, access):
        gap = _clean_concrete_modifier()
        del gap["armor_class"]                 # creature-c has ac_value 12
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-ac-missing" in codes

    def test_omitted_passive_fires(self, access):
        gap = _clean_concrete_modifier()
        del gap["passive_perception"]          # creature-c has passive 13
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-passive-missing" in codes

    def test_omitted_hit_dice_fires(self, access):
        gap = _clean_concrete_modifier()
        del gap["hit_dice"]                    # creature-c has hp_dice 2d6
        codes = {v.code for v in check(_sheet([gap]), access)}
        assert "companion-hit-dice-missing" in codes


# ── GREEN: a clean sheet passes ──────────────────────────────────────────────


class TestCleanSheetPasses:
    def test_hand_built_clean_sheet_has_no_violations(self, access):
        violations = check(_sheet([_clean_concrete_modifier()]), access)
        assert violations == []

    def test_derived_sheet_round_trips_clean(self, access):
        """The deriver's output validates cleanly against the independent check."""
        sheet, _ = derive_companions(_core(), None, "fill", access)
        violations = check({"core": _core(), "companion": sheet}, access)
        assert violations == []


# ── T111: illegal-companion fixture coverage (matches the non-harness gold negatives) ────


class TestT111IllegalCompanionCoverage:
    """F05-T111: the illegal-companion gold fixtures live outside the (green) harness and are
    verified rejected HERE. These synthetic scenarios mirror ``negative/companion/*.json``: a
    creature no owner confers, and a spell-summoned creature controlled below the summon's base
    spell level."""

    def test_ungranted_companion_rejected_on_legality_alone(self, access):
        # An ungranted creature (no grant_companion link) derived as a clean companion is rejected
        # ONLY by the legality gate — every other re-derived stat matches the catalog, so the sole
        # illegal finding is the legality code (mirrors companion-illegal-ungranted.json).
        core = _core(companions=[{"name": "Form", "db_creature_id": "creature-form"}])
        sheet, _ = derive_companions(core, None, "fill", access)
        illegal = {v.code for v in check({"core": core, "companion": sheet}, access)
                   if v.kind == "illegal"}
        assert illegal == {"companion-creature-illegal"}

    def test_spell_companion_below_base_level_rejected(self, access):
        # A spell-summoned creature controlled below the summon's base spell level is rejected by the
        # level gate (the analogue of the below-base-level cast gold negative).
        cm = _clean_spirit_modifier(cast_level=2)
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core(cast_level=2)), access)}
        assert "companion-creature-level-illegal" in codes


# ── state compatibility ──────────────────────────────────────────────────────


class TestStateCompatibility:
    def test_incompatible_companion_states_fire(self, access):
        cm = _clean_concrete_modifier()
        # raging BLOCKS concentrating in the shared state_compatibility catalog.
        cm["character_states"] = [
            {"state": "raging", "source": "x", "source_type": "feature"},
            {"state": "concentrating", "source": "y", "source_type": "spell"},
        ]
        violations = check(_sheet([cm]), access)
        assert any(v.code == "companion-state-incompatible" for v in violations)

    def test_compatible_companion_states_do_not_fire(self, access):
        cm = _clean_concrete_modifier()
        cm["character_states"] = [
            {"state": "raging", "source": "x", "source_type": "feature"},
            {"state": "inspired", "source": "y", "source_type": "feature"},
        ]
        violations = check(_sheet([cm]), access)
        assert not any(v.code == "companion-state-incompatible" for v in violations)


# ── templated creatures: independent re-derivation of the scaled values ──────


# GRIMOIRE source ability is the full DB id ('wisdom'); CORE keys abilities by the
# SHORT code ('wis') as real sheets do — the resolver must bridge the two.
_GRIM = {"sources": {"class:class-a": {"kind": "class", "ability": "wisdom", "cantrips_known": 0}},
         "spells": []}


def _spirit_core(cast_level=5, form="Form-Y"):
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


def _templated_sheet(cm, core):
    return {"core": core, "grimoire": _GRIM,
            "companion": {"schema_version": 1, "character_id": "cid",
                          "character_name": "Test", "companion_modifiers": [cm]}}


def _clean_spirit_modifier(cast_level=5, form="Form-Y"):
    # Values re-derived by hand from the formulas + owner ctx (cast 5, form Y, pb 3, wis 18):
    #   ac=15, hp=40, pb=3, Strike bonus 7 dmg "1d8 + 8", Burst (action) save_dc 15,
    #   Aura (non-action) save_dc 15, multiattack 2.
    return {
        "companion_index": 0,
        "armor_class": 15,
        "hit_points": {"max": 40, "current": 40, "temp": 0},
        "speed": {"walk": 30},
        "proficiency_bonus": 3,
        "multiattack": 2,
        "attacks": [
            {"name": "Strike", "attack_bonus": 7, "damage": "1d8 + 8"},
            {"name": "Burst", "save_dc": 15},
            {"name": "Aura", "save_dc": 15},
        ],
        "character_states": [],
    }


def _clean_beast_modifier():
    # cast N/A, owner level 4, pb 2, wis 16: ac=16, hp=25, pb=2, Strike B bonus 5 dmg "1d8 + 5".
    return {
        "companion_index": 0,
        "armor_class": 16,
        "hit_points": {"max": 25, "current": 25, "temp": 0},
        "speed": {"walk": 40},
        "proficiency_bonus": 2,
        "ability_scores": {"a1": 12, "a2": 14, "a3": 10},
        "saving_throws": [
            {"ability": "a1", "modifier": 1},
            {"ability": "a2", "modifier": 2},
            {"ability": "a3", "modifier": 0},
        ],
        "attacks": [{"name": "Strike B", "attack_bonus": 5, "damage": "1d8 + 5"}],
        "character_states": [],
    }


class TestTemplatedReDerivationFires:
    def test_wrong_scaled_hp_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["hit_points"]["max"] = 99
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-hp-mismatch" in codes

    def test_wrong_scaled_ac_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["armor_class"] = 99
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-ac-mismatch" in codes

    def test_wrong_scaled_attack_bonus_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["attacks"][0]["attack_bonus"] = 99
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-bonus-mismatch" in codes

    def test_wrong_scaled_damage_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["attacks"][0]["damage"] = "1d8 + 99"
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-damage-mismatch" in codes

    def test_wrong_scaled_action_save_dc_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["attacks"][1]["save_dc"] = 99          # Burst is an ACTION-scoped save
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-save-dc-mismatch" in codes

    def test_wrong_aura_save_dc_fires(self, access):
        # BLOCKER regression: a save DC on a NON-action (aura) trait must be re-checked,
        # not emitted-but-ignored. 'Aura' is a trait-kind save-forcing ability.
        cm = _clean_spirit_modifier()
        cm["attacks"][2]["save_dc"] = 99          # Aura is a trait-kind (non-action) save
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-save-dc-mismatch" in codes

    def test_wrong_multiattack_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["multiattack"] = 9
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-multiattack-mismatch" in codes

    def test_wrong_form_variant_hp_fires(self, access):
        # sheet HP is correct for Form-Y (40) but the companion was cast as Form-X (30)
        cm = _clean_spirit_modifier(form="Form-X")
        cm["hit_points"]["max"] = 40
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core(form="Form-X")), access)}
        assert "companion-hp-mismatch" in codes

    def test_wrong_beast_hp_scales_with_owner_level(self, access):
        cm = _clean_beast_modifier()          # correct for level 4 (25)
        codes = {v.code for v in check(_templated_sheet(cm, _beast_core(level=6)), access)}
        assert "companion-hp-mismatch" in codes    # level 6 expects 35


class TestTemplatedExpectedButOmittedFires:
    """A scaled field that the formula produces but the sheet OMITS is flagged
    incomplete — symmetry with the concrete slice's gap enforcement and AC's
    existing -missing branch."""

    def test_omitted_hp_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["hit_points"] = {"current": 40, "temp": 0}      # no max
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-hp-missing" in codes

    def test_omitted_pb_fires(self, access):
        cm = _clean_spirit_modifier()
        del cm["proficiency_bonus"]
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-pb-missing" in codes

    def test_omitted_multiattack_fires(self, access):
        cm = _clean_spirit_modifier()
        del cm["multiattack"]
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-multiattack-missing" in codes

    def test_omitted_attack_bonus_fires(self, access):
        cm = _clean_spirit_modifier()
        del cm["attacks"][0]["attack_bonus"]               # Strike
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-bonus-missing" in codes

    def test_omitted_attack_damage_fires(self, access):
        cm = _clean_spirit_modifier()
        del cm["attacks"][0]["damage"]                     # Strike
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-damage-missing" in codes

    def test_omitted_action_save_dc_fires(self, access):
        cm = _clean_spirit_modifier()
        del cm["attacks"][1]["save_dc"]                    # Burst (action)
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-save-dc-missing" in codes

    def test_omitted_aura_entry_fires(self, access):
        cm = _clean_spirit_modifier()
        cm["attacks"] = [a for a in cm["attacks"] if a["name"] != "Aura"]
        codes = {v.code for v in check(_templated_sheet(cm, _spirit_core()), access)}
        assert "companion-attack-missing" in codes


class TestTemplatedCleanPasses:
    def test_clean_spirit_has_no_violations(self, access):
        assert check(_templated_sheet(_clean_spirit_modifier(), _spirit_core()), access) == []

    def test_clean_beast_has_no_violations(self, access):
        assert check(_templated_sheet(_clean_beast_modifier(), _beast_core()), access) == []

    # NOTE: the two round-trip tests below are WIRING checks — they feed deriver
    # output straight into the check, and the deriver and validator hold DUPLICATE
    # (independent) copies of the owner-context + formula math, so agreement here only
    # proves the pipeline is wired. The genuine independence guarantee comes from the
    # hand-computed oracles in TestTemplatedReDerivationFires / _clean_*_modifier
    # (wrong value fires, correct passes), which never consult the deriver.
    def test_derived_spirit_round_trips_clean(self, access):
        core = _spirit_core()
        sheet, _ = derive_companions(core, None, "fill", access, _GRIM)
        assert check({"core": core, "grimoire": _GRIM, "companion": sheet}, access) == []

    def test_derived_beast_round_trips_clean(self, access):
        core = _beast_core()
        sheet, _ = derive_companions(core, None, "fill", access, _GRIM)
        assert check({"core": core, "grimoire": _GRIM, "companion": sheet}, access) == []
