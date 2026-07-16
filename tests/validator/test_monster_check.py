"""Tests for the standalone MONSTER validator (owner-less).

Content-neutral: synthetic creatures only. creature-c is a rich CONCRETE statblock;
creature-t is TEMPLATED (owner-scaled) and cannot stand alone. The check re-derives
each concrete field from the creature catalog independently — no owner context, no
deriver output.

T64: the standalone monster sheet references the bare shared stat-block base def
(no owner-linkage ``companion_index``), and the monster validator emits NATIVE
``monster-*`` check codes from the parametrised shared field-check helpers (not via
a post-hoc string rewrite of the codes).
"""
from app.derivation.monster import derive_monster_sheet
from validator.checks.monster import check


def _clean_stat_block():
    """A hand-built stat block matching creature-c exactly, built from the
    rule/catalog facts (not the deriver output). Owner-less: no companion_index."""
    return {
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


def _sheet(monsters):
    return {"schema_version": 1, "monsters": monsters}


def _monster(creature_id="creature-c", stat_block=None):
    return {"creature_id": creature_id,
            "stat_block": stat_block if stat_block is not None else _clean_stat_block()}


# ── GREEN: clean sheets pass ─────────────────────────────────────────────────


class TestCleanSheetPasses:
    def test_hand_built_clean_monster_has_no_violations(self, access):
        assert check(_sheet([_monster()]), access) == []

    def test_derived_sheet_round_trips_clean(self, access):
        """The deriver's output validates cleanly against the independent check."""
        sheet = derive_monster_sheet(access, ["creature-c"])
        assert check(sheet, access) == []

    def test_multiple_monsters_clean(self, access):
        sheet = _sheet([_monster(), _monster()])
        assert check(sheet, access) == []


# ── RED: a wrong stat is flagged with a NATIVE monster code ──────────────────


class TestWrongStatFires:
    def test_wrong_hp_fires(self, access):
        sb = _clean_stat_block()
        sb["hit_points"]["max"] = 99
        codes = {v.code for v in check(_sheet([_monster(stat_block=sb)]), access)}
        assert "monster-hp-mismatch" in codes

    def test_wrong_ac_fires(self, access):
        sb = _clean_stat_block()
        sb["armor_class"] = 99
        codes = {v.code for v in check(_sheet([_monster(stat_block=sb)]), access)}
        assert "monster-ac-mismatch" in codes

    def test_wrong_speed_fires(self, access):
        sb = _clean_stat_block()
        sb["speed"] = {"walk": 99}
        codes = {v.code for v in check(_sheet([_monster(stat_block=sb)]), access)}
        assert "monster-speed-mismatch" in codes

    def test_missing_attack_fires(self, access):
        sb = _clean_stat_block()
        sb["attacks"] = []
        codes = {v.code for v in check(_sheet([_monster(stat_block=sb)]), access)}
        assert "monster-attack-missing" in codes

    def test_no_companion_codes_ever_emitted(self, access):
        # The reused shared helpers must emit native codes only — never companion-*.
        sb = _clean_stat_block()
        sb["hit_points"]["max"] = 99
        sb["armor_class"] = 99
        sb["speed"] = {"walk": 99}
        codes = {v.code for v in check(_sheet([_monster(stat_block=sb)]), access)}
        assert not any(c.startswith("companion-") for c in codes)

    def test_wrong_stat_finding_is_retagged_to_monster_domain_and_path(self, access):
        sb = _clean_stat_block()
        sb["hit_points"]["max"] = 99
        v = next(x for x in check(_sheet([_monster(stat_block=sb)]), access)
                 if x.code == "monster-hp-mismatch")
        assert v.domain == "monster"
        assert v.path == "monsters.0.stat_block.hit_points.max"
        assert v.message.startswith("monster 0:")

    def test_retag_fires_for_non_hp_field_armor_class(self, access):
        # Guard against silent path/message format drift in the reused shared helpers
        # for a field OTHER than HP (armor_class lives at a different depth).
        sb = _clean_stat_block()
        sb["armor_class"] = 99
        v = next(x for x in check(_sheet([_monster(stat_block=sb)]), access)
                 if x.code == "monster-ac-mismatch")
        assert v.domain == "monster"
        assert v.path == "monsters.0.stat_block.armor_class"
        assert v.message.startswith("monster 0:")

    def test_retag_fires_for_deeper_field_defenses(self, access):
        # A deeper nested path (defenses.<label>) must also retag cleanly.
        sb = _clean_stat_block()
        sb["defenses"]["resistance"] = []          # drop catalogued fire resistance
        v = next(x for x in check(_sheet([_monster(stat_block=sb)]), access)
                 if x.code == "monster-defense-subset-violation")
        assert v.domain == "monster"
        assert v.path is not None and v.path.startswith("monsters.0.stat_block.defenses")
        assert v.message.startswith("monster 0:")

    def test_retag_uses_correct_index_for_second_monster(self, access):
        # The retag is per-index: a fault on monster 1 must land under monsters.1.*.
        sb = _clean_stat_block()
        sb["speed"] = {"walk": 99}
        sheet = _sheet([_monster(), _monster(stat_block=sb)])
        v = next(x for x in check(sheet, access)
                 if x.code == "monster-speed-mismatch")
        assert v.domain == "monster"
        assert v.path == "monsters.1.stat_block.speed"
        assert v.message.startswith("monster 1:")


# ── save proficiency (T63): re-derived owner-less on a standalone monster ─────


def _sp_stat_block():
    """A hand-built stat block matching creature-sp (pb=3, a2 proficient): the a2 save is
    ability mod (+3) PLUS pb (3); a1/a3 are plain ability modifiers. Owner-less."""
    return {
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


class TestMonsterSaveProficiency:
    def test_clean_proficient_save_passes(self, access):
        sheet = _sheet([_monster(creature_id="creature-sp", stat_block=_sp_stat_block())])
        assert not any(v.code.startswith("monster-save") for v in check(sheet, access))

    def test_derived_proficient_save_round_trips_clean(self, access):
        sheet = derive_monster_sheet(access, ["creature-sp"])
        assert not any(v.code.startswith("monster-save") for v in check(sheet, access))

    def test_proficient_save_without_pb_fires(self, access):
        sb = _sp_stat_block()
        sb["saving_throws"][1]["modifier"] = 3           # a2 missing pb
        sheet = _sheet([_monster(creature_id="creature-sp", stat_block=sb)])
        codes = {v.code for v in check(sheet, access)}
        assert "monster-save-mismatch" in codes


# ── RED: a templated creature is rejected standalone ─────────────────────────


class TestTemplatedRejected:
    def test_templated_creature_flagged_not_standalone(self, access):
        # creature-t is owner-scaled; a monster sheet claiming it must be rejected,
        # NOT validated against un-scaled zeros.
        sheet = _sheet([_monster(creature_id="creature-t", stat_block=_clean_stat_block())])
        codes = {v.code for v in check(sheet, access)}
        assert "monster-templated-not-standalone" in codes

    def test_templated_rejection_short_circuits_concrete_checks(self, access):
        # Once rejected, the concrete re-derivation must not also run (no stat mismatch noise).
        sheet = _sheet([_monster(creature_id="creature-t", stat_block=_clean_stat_block())])
        codes = {v.code for v in check(sheet, access)}
        assert not any(c.endswith("-mismatch") or c.endswith("-missing") for c in codes)


# ── RED: structural rejections ───────────────────────────────────────────────


class TestStructuralRejections:
    def test_unknown_creature_fires(self, access):
        sheet = _sheet([_monster(creature_id="no-such-creature")])
        codes = {v.code for v in check(sheet, access)}
        assert "monster-creature-unknown" in codes

    def test_missing_creature_id_fires(self, access):
        sheet = _sheet([{"stat_block": _clean_stat_block()}])
        codes = {v.code for v in check(sheet, access)}
        assert "monster-creature-missing-id" in codes

    def test_missing_stat_block_fires(self, access):
        sheet = _sheet([{"creature_id": "creature-c"}])
        codes = {v.code for v in check(sheet, access)}
        assert "monster-stat-block-missing" in codes


# ── state compatibility (reused, re-tagged, native code) ─────────────────────


class TestStateCompatibility:
    def test_incompatible_states_fire(self, access):
        sb = _clean_stat_block()
        sb["character_states"] = [
            {"state": "raging", "source": "x", "source_type": "feature"},
            {"state": "concentrating", "source": "y", "source_type": "spell"},
        ]
        v = check(_sheet([_monster(stat_block=sb)]), access)
        assert any(x.code == "monster-state-incompatible" and x.domain == "monster" for x in v)

    def test_compatible_states_do_not_fire(self, access):
        sb = _clean_stat_block()
        sb["character_states"] = [
            {"state": "raging", "source": "x", "source_type": "feature"},
            {"state": "inspired", "source": "y", "source_type": "feature"},
        ]
        v = check(_sheet([_monster(stat_block=sb)]), access)
        assert not any(x.code == "monster-state-incompatible" for x in v)
