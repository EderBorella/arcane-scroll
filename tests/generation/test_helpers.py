"""Generation helpers (the pure compute): ability assignment, skills, spell pools, subclass
resolution, repair, race bonus. All deterministic against the synthetic catalog."""
import random

from app.generation import helpers as H


def test_ability_assignment_by_priority(catalog):
    aa = H.ability_assignment(catalog, [("mage", 5, None)])
    assert sorted(aa.values(), reverse=True) == [15, 14, 13, 12, 10, 8]
    assert aa["int"] == 15      # mage priority leads with int
    assert aa["str"] == 8       # ...and ends with str


def test_ability_assignment_multiclass_combines_priority(catalog):
    aa = H.ability_assignment(catalog, [("fighter", 5, None), ("mage", 5, None)])
    assert sorted(aa.values(), reverse=True) == [15, 14, 13, 12, 10, 8]
    assert aa["int"] >= 13                      # mage's primary no longer dumped (was 8 for a lone fighter)
    assert max(aa["str"], aa["dex"]) >= 13      # a martial stat still high


def test_ability_assignment_subclass_override(catalog):
    assert H.ability_assignment(catalog, [("warrior", 5, None)])["str"] == 15        # warrior base: str first
    assert H.ability_assignment(catalog, [("warrior", 5, "Berserker")])["con"] == 15  # subclass override: con first


def test_required_abilities(catalog):
    assert H.required_abilities(catalog, [("warrior", 3, None), ("mage", 2, None)]) == {"str", "con", "int"}
    assert H.required_abilities(catalog, [("mage", 5, None)]) == set()                # single class: no prereq


def test_class_skill_grant_and_names(catalog):
    n, idx = H.class_skill_grant(catalog, "mage")
    assert n == 2
    assert H.skill_names(catalog, idx) == ["Focus", "Lore", "Runes"]


def test_spell_pools_counts_for_caster(catalog):
    aa = H.ability_assignment(catalog, [("mage", 5, "Evoker")])
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


def test_spell_pools_prepared_caster(catalog):
    aa = H.ability_assignment(catalog, [("oracle", 3, "Seer")])     # wis = 15
    cant, spl, nc, ns = H.spell_pools(catalog, [("oracle", 3, "Seer")], "Human", aa)
    assert nc == 2           # cantrips known (3) capped at the oracle cantrip pool (2)
    assert ns == 5           # prepared: wis mod (2) + level (3)
    assert len(spl) == 6     # oracle leveled spells up to L2


def test_spell_pools_multiclass(catalog):
    aa = H.ability_assignment(catalog, [("mage", 3, "Evoker"), ("oracle", 3, "Seer")])  # combined priority
    cant, spl, nc, ns = H.spell_pools(catalog, [("mage", 3, "Evoker"), ("oracle", 3, "Seer")], "Human", aa)
    assert len(cant) == 5 and nc == 5                # union cantrip pool; 3+3 capped at 5
    assert len(spl) == 7                              # union of both leveled lists (≤ L2)
    assert ns == 7                                    # mage known (6) + oracle prepared (1+3=4) = 10, capped at 7


def test_repair_dedups_and_pads_spells(catalog):
    ch = {"skill_choices": ["Lore", "Runes"],
          "spell_choices": {"cantrips": ["Spark", "Spark", "Glimmer", "Whisper"],
                            "spells": ["Bolt", "Bolt", "Ward", "Mist", "Veil", "Quake", "Gale", "Snare"]}}
    H.repair(catalog, ch, "Human", [("mage", 5)], ["Evoker"])
    c = ch["spell_choices"]
    assert len(c["cantrips"]) == 4 and len(set(c["cantrips"])) == 4
    assert len(c["spells"]) == 8 and len(set(c["spells"])) == 8


def test_resolve_subclasses_multiclass(catalog):
    out = H.resolve_subclasses(catalog, [("mage", 5), ("oracle", 1)], rng=random.Random(0))
    assert out[0] in ("Evoker", "Abjurer")    # mage unlocks at L2
    assert out[1] is None                      # oracle unlocks at L3, so L1 → none


def test_patron_expanded(catalog):
    assert H._patron_expanded(catalog, [("warlock", 5, "shadow")], 2) == {"Bolt", "Quake"}
    assert H._patron_expanded(catalog, [("warlock", 5, "shadow")], 1) == {"Bolt"}
    assert H._patron_expanded(catalog, [("mage", 5, "Evoker")], 2) == set()   # non-warlock → none


def test_skin_options(catalog):
    assert H.skin_options(catalog, "Scaled") == ["Bronze", "Silver"]          # race override
    assert H.skin_options(catalog, "Human") == catalog.get("skin_default")    # default palette


def test_school_spells_filters_by_class_school_and_level(catalog):
    assert H.school_spells(catalog, "wizard", None, 0, 0) == ["Wiz Cantrip A", "Wiz Cantrip B"]  # cantrips
    assert H.school_spells(catalog, "wizard", {"abjuration", "evocation"}, 1, 1) == ["Evoke Bolt", "Ward Sigil"]
    assert "Charm Word" in H.school_spells(catalog, None, None, 1, 1)         # ci=None → any class


def test_all_skill_names(catalog):
    assert H.all_skill_names(catalog) == ["Brawn", "Focus", "Lore", "Menace", "Perception", "Runes", "Watch"]
