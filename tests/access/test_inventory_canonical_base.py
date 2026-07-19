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


# ── magic armour / shield base resolution (F05-T145) ──────────────────────────


def test_resolve_armor_base_single_template(access):
    # 'mi-armor' has no armor row of its own; its single template base is 'armor-d'.
    assert inv_q.resolve_armor_base(access, "mi-armor") == "armor-d"


def test_resolve_armor_base_sheet_choice_by_id(access):
    # A generic magic armour with no template base resolves via the sheet's chosen base id.
    assert inv_q.resolve_armor_base(access, "mi-armor-generic", "armor-e") == "armor-e"


def test_resolve_armor_base_sheet_choice_by_name(access):
    # The sheet-chosen base may be a display name, resolved through the catalogue.
    assert inv_q.resolve_armor_base(access, "mi-armor-generic", "Armor B") == "armor-e"


def test_resolve_armor_base_sheet_choice_overrides_template(access):
    # When the sheet records a base, it wins over the template's default.
    assert inv_q.resolve_armor_base(access, "mi-armor", "armor-e") == "armor-e"


def test_resolve_armor_base_unresolved_returns_none(access):
    # A generic magic armour with no template base and no sheet choice cannot be resolved.
    assert inv_q.resolve_armor_base(access, "mi-armor-generic") is None


def test_resolve_armor_base_direct_armor_row(access):
    # A mundane armour id (its own armor row) resolves to itself.
    assert inv_q.resolve_armor_base(access, "armor-d") == "armor-d"


def test_resolve_shield_base_returns_mundane_shield(access):
    # A magic shield (no armor row) re-derives its base from the mundane shield (+2).
    assert inv_q.resolve_shield_base(access, "mi-shield") == "shield-item"
