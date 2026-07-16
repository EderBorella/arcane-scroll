"""Tests for the COMPANION validator (concrete-creature slice).

Content-neutral: synthetic creatures only (creature-a templated, creature-b empty,
creature-c a rich concrete statblock). The check re-derives each fixed-stat field
from the creature catalog independently of any deriver output.
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


# ── templated creature is deferred (no numeric checks) ───────────────────────


class TestTemplatedDeferred:
    def test_templated_creature_skips_numeric_checks(self, access):
        # creature-a carries a creature_formula row -> templated -> numeric re-derivation
        # is deferred. A stub with only the required fields must NOT fire numeric codes.
        core = _core(companions=[{"name": "Templated", "db_creature_id": "creature-a"}])
        stub = {"companion_index": 0,
                "hit_points": {"max": 10, "current": 10, "temp": 0},
                "speed": {"walk": 30}}
        violations = check(_sheet([stub], core=core), access)
        numeric = {"companion-hp-mismatch", "companion-speed-mismatch",
                   "companion-attack-missing", "companion-abilities-mismatch"}
        assert not (numeric & {v.code for v in violations})
