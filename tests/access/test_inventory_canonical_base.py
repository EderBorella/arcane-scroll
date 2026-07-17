"""Access-layer tests for the canonical base-weapon resolution (T121).

A magic weapon template may name several base weapons. The reader returns a
DETERMINISTIC canonical base (the lowest id among the bases that resolve to a
real weapon-stats row) so the attack-bonus and extra-damage rider re-derivation
is not silently skipped for a multi-base template."""
from access.validator import inventory as inv_q


def test_single_base_template_resolves(access):
    # 'mi-relic-blade' names one base (weapon-a) with a real weapon row.
    assert inv_q.base_weapon_id_for_item(access, "mi-relic-blade") == "weapon-a"


def test_multi_base_template_resolves_lowest_id(access):
    # 'mi-ambi-blade' names weapon-a and weapon-b; both have weapon rows, so the
    # canonical base is the lowest id, weapon-a.
    assert inv_q.base_weapon_id_for_item(access, "mi-ambi-blade") == "weapon-a"


def test_unknown_template_returns_none(access):
    assert inv_q.base_weapon_id_for_item(access, "mi-does-not-exist") is None


def test_weapon_attack_facts_uses_canonical_base(access):
    # A stats-less multi-base magic weapon now yields facts via its canonical base.
    facts = inv_q.weapon_attack_facts(access, "mi-ambi-blade")
    assert facts is not None
    assert facts["tier_id"] == "martial"        # weapon-a is martial
    assert facts["range_class_id"] == "melee"
