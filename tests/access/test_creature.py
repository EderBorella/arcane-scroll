"""Tests for the creature access layer (L15 statblock reads + L21 companion links).

Pure-query coverage: every reader returns raw rows as stored, with no rule math.
Content-neutral: synthetic creatures (creature-a / creature-b) only.
"""
from access.validator import creature as cr


class TestCreatureHeader:
    def test_row_returns_identity_and_facts(self, access):
        row = cr.creature_row(access, "creature-a")
        assert row is not None
        assert row["name"] == "Creature A2"
        assert row["size_id"] == "size-a"
        assert row["creature_type_id"] == "type-a"
        assert row["ac_value"] == 13
        assert row["hp_average"] == 10
        assert row["cr_text"] == "1/4"

    def test_row_unknown_creature_is_none(self, access):
        assert cr.creature_row(access, "no-such-creature") is None


class TestCreatureChildFacts:
    def test_abilities(self, access):
        rows = cr.creature_abilities(access, "creature-a")
        assert {r["ability_id"]: r["score"] for r in rows} == {"a1": 12, "a2": 14, "a3": 10}

    def test_speeds_feet_and_formula(self, access):
        rows = {r["movement_mode_id"]: r for r in cr.creature_speeds(access, "creature-a")}
        assert rows["walk"]["feet"] == 30
        assert rows["fly"]["feet"] == 60
        # a templated speed carries a formula_note instead of feet
        assert rows["swim"]["feet"] is None
        assert rows["swim"]["formula_note"] == "equal to its Walk Speed"

    def test_senses(self, access):
        rows = cr.creature_senses(access, "creature-a")
        assert {r["sense_id"]: r["range_ft"] for r in rows} == {"darkvision": 60}

    def test_skills(self, access):
        rows = cr.creature_skills(access, "creature-a")
        assert {r["skill_id"]: r["bonus"] for r in rows} == {"sk1": 4}

    def test_passive_perception(self, access):
        assert cr.creature_passive_perception(access, "creature-a") == 12

    def test_passive_perception_absent_is_none(self, access):
        assert cr.creature_passive_perception(access, "creature-b") is None


class TestCreatureDefenses:
    def test_split_by_kind(self, access):
        d = cr.creature_defenses(access, "creature-a")
        assert [r["damage_type_id"] for r in d["resistance"]] == ["fire"]
        assert [r["damage_type_id"] for r in d["immunity_damage"]] == ["poison"]
        assert [r["condition_id"] for r in d["immunity_condition"]] == ["poisoned"]
        assert [r["damage_type_id"] for r in d["vulnerability"]] == ["cold"]

    def test_immunity_damage_and_condition_are_separated(self, access):
        d = cr.creature_defenses(access, "creature-a")
        # the split is by populated column: damage-immunity rows project the
        # damage type, condition-immunity rows project the condition
        assert all("damage_type_id" in r.keys() for r in d["immunity_damage"])
        assert all("condition_id" in r.keys() for r in d["immunity_condition"])
        # both immunity kinds are present for this creature (one of each)
        assert len(d["immunity_damage"]) == 1
        assert len(d["immunity_condition"]) == 1

    def test_empty_defenses(self, access):
        d = cr.creature_defenses(access, "creature-b")
        assert d == {"resistance": [], "immunity_damage": [],
                     "immunity_condition": [], "vulnerability": []}


class TestCreatureTraitsAndActions:
    def test_traits_only_kind_trait(self, access):
        rows = cr.creature_traits(access, "creature-a")
        assert [r["name"] for r in rows] == ["Trait A"]
        assert all(r["kind"] == "trait" for r in rows)

    def test_actions_exclude_traits(self, access):
        rows = cr.creature_actions(access, "creature-a")
        names = {r["name"] for r in rows}
        assert names == {"Action A", "Action B"}
        assert all(r["kind"] in ("action", "bonus_action", "reaction") for r in rows)

    def test_action_attack_facts_are_raw(self, access):
        rows = {r["name"]: r for r in cr.creature_actions(access, "creature-a")}
        atk = rows["Action A"]
        assert atk["atk_bonus"] == 4
        assert atk["reach_ft"] == 5
        assert atk["dmg_dice"] == "1d6 + 2"
        assert atk["damage_type_id"] == "fire"
        recharge = rows["Action B"]
        assert recharge["recharge_min"] == 5
        assert recharge["uses_per_day"] == 3

    def test_no_traits_or_actions(self, access):
        assert cr.creature_traits(access, "creature-b") == []
        assert cr.creature_actions(access, "creature-b") == []


class TestCreatureFormulas:
    def test_formula_header(self, access):
        rows = cr.creature_formulas(access, "creature-a")
        assert len(rows) == 1
        assert rows[0]["target"] == "attack_bonus"
        assert rows[0]["trait_id"] == "ct-a-act"
        assert rows[0]["base"] == 4

    def test_formula_terms(self, access):
        terms = cr.creature_formula_terms(access, "cf-a-atk")
        assert len(terms) == 1
        assert terms[0]["coefficient"] == 1.0
        assert terms[0]["variable"] == "owner_proficiency_bonus"

    def test_no_formulas(self, access):
        assert cr.creature_formulas(access, "creature-b") == []
        assert cr.creature_formula_terms(access, "no-such-formula") == []


class TestCompanionGrants:
    def test_spell_owner_link(self, access):
        rows = cr.companion_grants(access, "spell", "sp-companion")
        assert len(rows) == 1
        g = rows[0]
        assert g["creature_id"] == "creature-a"
        assert g["at_spell_level"] == 2
        assert g["duration_amount"] == 1
        assert g["duration_unit_id"] == "hour"

    def test_unknown_owner_empty(self, access):
        assert cr.companion_grants(access, "spell", "no-such-owner") == []

    def test_level_gate_excludes_below_gained_at_level(self, access):
        # the subclass companion is gained at level 3
        assert cr.companion_grants(access, "subclass", "sub-companion", at_level=2) == []

    def test_level_gate_includes_at_or_above(self, access):
        rows = cr.companion_grants(access, "subclass", "sub-companion", at_level=3)
        assert [r["creature_id"] for r in rows] == ["creature-b"]

    def test_always_on_grant_survives_level_gate(self, access):
        # the spell link has NULL gained_at_level -> always applies, even at level 1
        rows = cr.companion_grants(access, "spell", "sp-companion", at_level=1)
        assert [r["creature_id"] for r in rows] == ["creature-a"]
