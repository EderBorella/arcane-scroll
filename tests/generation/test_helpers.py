"""Generation helpers (the pure compute): ability assignment, skills, spell pools, subclass
resolution, repair, race bonus. All deterministic against the synthetic catalog."""
import random

from app.generation import helpers as H


def test_ability_assignment_by_priority(catalog):
    aa = H.ability_assignment(catalog, "mage")
    assert sorted(aa.values(), reverse=True) == [15, 14, 13, 12, 10, 8]
    assert aa["int"] == 15      # mage priority leads with int
    assert aa["str"] == 8       # ...and ends with str


def test_class_skill_grant_and_names(catalog):
    n, idx = H.class_skill_grant(catalog, "mage")
    assert n == 2
    assert H.skill_names(catalog, idx) == ["Focus", "Lore", "Runes"]


def test_spell_pools_counts_for_caster(catalog):
    aa = H.ability_assignment(catalog, "mage")
    cant, spl, nc, ns = H.spell_pools(catalog, [("mage", 5, "Evoker")], "human", aa)
    assert nc == 4               # cantrips known at L5
    assert ns == 8               # known-caster spells known at L5
    assert len(cant) == 5        # full cantrip pool
    assert "Ember" in spl        # a level-3 spell is in range at L5


def test_spell_pools_none_for_noncaster(catalog):
    assert H.spell_pools(catalog, [("warrior", 3, "Champion")], "human", {}) is None


def test_resolve_subclasses_locked_random_and_override(catalog):
    rng = random.Random(0)
    assert H.resolve_subclasses(catalog, [("mage", 1)], rng=rng) == [None]      # below unlock level
    picked = H.resolve_subclasses(catalog, [("mage", 3)], rng=rng)[0]
    assert picked in ("Evoker", "Abjurer")                                       # random from options
    assert H.resolve_subclasses(catalog, [("mage", 3)], overrides={"mage": "Abjurer"})[0] == "Abjurer"


def test_repair_dedups_and_pads_skills(catalog):
    ch = {"skill_choices": ["Lore", "Lore"]}          # duplicate; grant is 2
    H.repair(catalog, ch, "human", [("mage", 1)], [None])
    assert len(ch["skill_choices"]) == 2
    assert len(set(ch["skill_choices"])) == 2


def test_race_bonus(catalog):
    assert H.race_bonus(catalog, "human", "int") == 1
    assert H.race_bonus(catalog, "human", "str") == 0
