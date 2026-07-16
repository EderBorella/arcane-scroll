"""Catalog name/enumeration readers on the generator DAL (F05-T67), against the synthetic rules DB."""
import pytest

from access.generator import catalog


def test_name_of_resolves_display_names(gen_access):
    assert catalog.name_of(gen_access, "species", "species-a") == "Species A"
    assert catalog.name_of(gen_access, "subclass", "sub-a") == "Sub A"
    assert catalog.name_of(gen_access, "weapon_tier", "simple") == "Simple"


def test_name_of_unknown_id_is_none(gen_access):
    assert catalog.name_of(gen_access, "species", "nope") is None
    assert catalog.name_of(gen_access, "tool", None) is None


def test_name_of_rejects_unlisted_dimension(gen_access):
    with pytest.raises(ValueError):
        catalog.name_of(gen_access, "grant_proficiency", "x")


def test_list_abilities_ordered(gen_access):
    rows = catalog.list_abilities(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert {"id", "name", "abbrev"} <= set(rows[0].keys())


def test_list_skills_ordered_with_ability(gen_access):
    rows = catalog.list_skills(gen_access)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert all(r["ability_id"] for r in rows)
