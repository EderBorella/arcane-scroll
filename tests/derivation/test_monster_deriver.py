"""Tests for the standalone MONSTER materialization deriver.

Content-neutral: synthetic creatures only. creature-c is a rich CONCRETE statblock
(materialisable standalone); creature-a / creature-t / creature-tb carry
creature_formula rows (TEMPLATED, owner-scaled) and CANNOT stand alone.
"""
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.derivation.monster import (
    MonsterMaterializationError,
    derive_monster,
    derive_monster_sheet,
)

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"
_MONSTER = json.loads((_CONTRACTS / "monster-sheet.schema.json").read_text())
_COMPANION = json.loads((_CONTRACTS / "companion-modifier.schema.json").read_text())
# Registry so the monster sheet's external $ref to companionModifier resolves.
_REGISTRY = Registry().with_resources([
    (_MONSTER["$id"], Resource.from_contents(_MONSTER)),
    (_COMPANION["$id"], Resource.from_contents(_COMPANION)),
])
_VALIDATOR = Draft202012Validator(_MONSTER, registry=_REGISTRY)


def _schema_errors(sheet) -> list:
    return sorted(f"{list(e.path)}: {e.message}" for e in _VALIDATOR.iter_errors(sheet))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(_MONSTER)


class TestConcreteMaterialization:
    def test_single_concrete_monster_reuses_companion_statblock(self, access):
        entry = derive_monster(access, "creature-c")
        assert entry["creature_id"] == "creature-c"
        sb = entry["stat_block"]
        # T64: the owner-less monster sheet references the bare shared base def — no
        # owner-linkage index leaks onto it.
        assert "companion_index" not in sb
        assert sb["ability_scores"] == {"a1": 8, "a2": 16, "a3": 12}
        assert sb["armor_class"] == 12
        assert sb["hit_points"] == {"max": 7, "current": 7, "temp": 0}
        assert sb["hit_dice"] == {"d6": {"max": 2, "remaining": 2}}
        assert sb["speed"] == {"walk": 30, "fly": 40, "swim": 30}
        assert sb["senses"] == {"darkvision": 90}
        assert sb["attacks"] == [
            {"name": "Bite", "attack_bonus": 5, "damage": "1d6 + 3", "damage_type": "fire"}]
        assert sb["character_states"] == []

    def test_stat_blocks_omit_owner_linkage_index(self, access):
        # T64: position is tracked by the monsters[] array itself, not by a
        # companion_index on each owner-less stat block.
        sheet = derive_monster_sheet(access, ["creature-c", "creature-c"])
        assert [m["creature_id"] for m in sheet["monsters"]] == ["creature-c", "creature-c"]
        assert all("companion_index" not in m["stat_block"] for m in sheet["monsters"])

    def test_sheet_shape(self, access):
        sheet = derive_monster_sheet(access, ["creature-c"])
        assert sheet["schema_version"] == 1
        assert len(sheet["monsters"]) == 1
        assert sheet["monsters"][0]["creature_id"] == "creature-c"

    def test_empty_creature_list_yields_empty_sheet(self, access):
        assert derive_monster_sheet(access, []) == {"schema_version": 1, "monsters": []}


class TestTemplatedRejected:
    @pytest.mark.parametrize("creature_id", ["creature-a", "creature-t", "creature-tb"])
    def test_templated_creature_cannot_stand_alone(self, access, creature_id):
        with pytest.raises(MonsterMaterializationError) as exc:
            derive_monster(access, creature_id)
        assert "templated" in str(exc.value)

    def test_sheet_derivation_fails_fast_on_templated(self, access):
        with pytest.raises(MonsterMaterializationError):
            derive_monster_sheet(access, ["creature-c", "creature-t"])


class TestUnknownRejected:
    def test_unknown_creature_rejected(self, access):
        with pytest.raises(MonsterMaterializationError) as exc:
            derive_monster(access, "no-such-creature")
        assert "catalogue" in str(exc.value)


class TestSchemaConformance:
    def test_concrete_sheet_validates(self, access):
        sheet = derive_monster_sheet(access, ["creature-c"])
        assert _schema_errors(sheet) == []

    def test_multi_monster_sheet_validates(self, access):
        sheet = derive_monster_sheet(access, ["creature-c", "creature-c"])
        assert _schema_errors(sheet) == []
