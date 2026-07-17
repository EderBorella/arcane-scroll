from validator.checks.grimoire import check
from validator.checks import ALL_CHECKS
from validator.checks import spellcasting as sc


def _make_sheet(**overrides):
    """Minimal merged CORE+GRIMOIRE dict for the grimoire check."""
    sheet = {
        "identity": {
            "name": "Test", "species": "Species A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None}],
            "background": "Background A",
        },
        "feats": [],
        "features": [],
        "proficiency_bonus": 2,
        "sources": {},
        "spells": [],
        "spell_slots": None,
        "pact_slots": None,
    }
    sheet.update(overrides)
    return sheet


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ── ported checks ────────────────────────────────────────────────────────────


def test_valid_minimal(access):
    assert check(_make_sheet(), access) == []


def test_valid_full_caster(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "save_dc": 12, "attack_bonus": 4,
                                   "cantrips_known": 2, "prepared_limit": 3}},
        spells=[
            {"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
            {"name": "Sp2", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
            {"name": "Sp3", "level": 1, "bucket": "prepared", "source": "class:class-a"},
        ],
        spell_slots={"1": {"max": 4}, "2": {"max": 2}},
    )
    assert check(sheet, access) == []


def test_dc_mismatch(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "save_dc": 99, "attack_bonus": 4}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"}],
    )
    assert "spell-save-dc-mismatch" in _codes(sheet, access)


def test_attack_mismatch(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "save_dc": 12, "attack_bonus": 99}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"}],
    )
    assert "spell-attack-mismatch" in _codes(sheet, access)


def test_budget_too_high_cantrips(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "cantrips_known": 99}},
    )
    assert "source-budget-too-high" in _codes(sheet, access)


def test_budget_too_high_prepared(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "prepared_limit": 99}},
    )
    assert "source-budget-too-high" in _codes(sheet, access)


def test_too_many_cantrip_spells(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "cantrips_known": 1}},
        spells=[
            {"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
            {"name": "Sp2", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
        ],
    )
    assert "too-many-cantrips" in _codes(sheet, access)


def test_too_many_prepared_spells(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "prepared_limit": 1}},
        spells=[
            {"name": "Sp3", "level": 1, "bucket": "prepared", "source": "class:class-a"},
            {"name": "Sp4", "level": 1, "bucket": "prepared", "source": "class:class-a"},
        ],
    )
    assert "too-many-prepared" in _codes(sheet, access)


def test_known_not_counted_against_budget(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "prepared_limit": 1}},
        spells=[
            {"name": "Sp3", "level": 1, "bucket": "prepared", "source": "class:class-a"},
            {"name": "Sp4", "level": 1, "bucket": "known", "source": "class:class-a"},
        ],
    )
    assert "too-many-prepared" not in _codes(sheet, access)


def test_spell_slots_mismatch(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spell_slots={"1": {"max": 99}},
    )
    assert "spell-slots-mismatch" in _codes(sheet, access)


def test_pact_slots_mismatch(access):
    sheet = _make_sheet(
        identity={"classes": [{"class": "Class P", "level": 2}]},
        sources={"class:class-p": {"kind": "class", "ability": "a1", "modifier": 2}},
        pact_slots={"1": {"max": 99}},
    )
    assert "pact-slots-mismatch" in _codes(sheet, access)


def test_unexpected_pact_slots(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        pact_slots={"1": {"max": 2}},
    )
    assert "unexpected-pact-slots" in _codes(sheet, access)


def test_pact_over_spells_known_flagged(access):
    """A pact caster over the DB spells-known count is flagged INDEPENDENTLY — even when the source
    declares no prepared_limit (the historically-uncapped shape). class-p knows 3 leveled spells at
    level 2; four prepared exceeds that."""
    sheet = _make_sheet(
        identity={"classes": [{"class": "Class P", "level": 2}]},
        sources={"class:class-p": {"kind": "class", "ability": "a1"}},
        spells=[{"name": n, "level": 1, "bucket": "prepared", "source": "class:class-p"}
                for n in ("Sp3", "Sp7", "Sp8", "Sp9")],
        pact_slots={"1": {"max": 2}},
    )
    assert "too-many-prepared" in _codes(sheet, access)


def test_pact_at_spells_known_legal(access):
    """Exactly the DB spells-known count is legal: three prepared for a level-2 class-p caster."""
    sheet = _make_sheet(
        identity={"classes": [{"class": "Class P", "level": 2}]},
        sources={"class:class-p": {"kind": "class", "ability": "a1"}},
        spells=[{"name": n, "level": 1, "bucket": "prepared", "source": "class:class-p"}
                for n in ("Sp3", "Sp7", "Sp8")],
        pact_slots={"1": {"max": 2}},
    )
    assert "too-many-prepared" not in _codes(sheet, access)


def test_spell_duplicate(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[
            {"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
            {"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"},
        ],
    )
    assert "spell-duplicate" in _codes(sheet, access)


def test_unknown_spell(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Nonexistent Spell", "level": 0, "bucket": "cantrip",
                 "source": "class:class-a"}],
    )
    assert "unknown-spell" in _codes(sheet, access)


def test_spell_not_on_list(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp4", "level": 1, "bucket": "prepared", "source": "class:class-a"}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": None}],
                  "species": None},
    )
    assert "spell-not-on-list" in _codes(sheet, access)


def test_class_list_bucket_exempt_from_list_check(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp4", "level": 1, "bucket": "class_list", "source": "class:class-a"}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": None}],
                  "species": None},
    )
    assert "spell-not-on-list" not in _codes(sheet, access)


# ── new grimoire-specific checks ─────────────────────────────────────────────


def test_class_list_not_granted(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp4", "level": 1, "bucket": "class_list", "source": "class:class-a"}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": None}],
                  "species": None},
    )
    assert "class-list-not-granted" in _codes(sheet, access)


def test_class_list_valid_from_subclass_grant(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp5", "level": 1, "bucket": "class_list", "source": "subclass:sub-widen"}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": "Sub Widen"}],
                  "species": None},
    )
    codes = _codes(sheet, access)
    assert "class-list-not-granted" not in codes


def test_cantrip_wrong_recovery(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a",
                 "recovery": "spell_slot"}],
    )
    assert "invalid-recovery" in _codes(sheet, access)


def test_ritual_only_without_ritual_tag(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1 Ritual", "level": 1, "bucket": "always",
                 "source": "subclass:sub-widen", "recovery": "ritual_only",
                 "ritual_castable": False}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": "Sub Widen"}],
                  "species": None},
    )
    codes = _codes(sheet, access)
    assert "invalid-recovery" in codes


def test_ritual_only_valid_with_ritual_tag(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1 Ritual", "level": 1, "bucket": "always",
                 "source": "subclass:sub-widen", "recovery": "ritual_only",
                 "ritual_castable": True}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": "Sub Widen"}],
                  "species": None},
    )
    assert "invalid-recovery" not in _codes(sheet, access)


def test_slotless_without_uses(access):
    sheet = _make_sheet(
        sources={"species:species-slotless": {"kind": "species", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp2", "level": 0, "bucket": "always",
                 "source": "species:species-slotless", "recovery": "slotless_per_rest"}],
        identity={"classes": [], "species": "Species Slotless"},
    )
    codes = _codes(sheet, access)
    assert "invalid-recovery" in codes


def test_slotless_with_uses_valid(access):
    sheet = _make_sheet(
        sources={"species:species-slotless": {"kind": "species", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp2", "level": 0, "bucket": "always",
                 "source": "species:species-slotless", "recovery": "slotless_per_rest",
                 "uses": {"max": 3, "recharge": "short-rest"}}],
        identity={"classes": [], "species": "Species Slotless"},
    )
    assert "invalid-recovery" not in _codes(sheet, access)


def test_ritual_castable_mismatch(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1 Ritual", "level": 1, "bucket": "prepared",
                 "source": "class:class-a", "ritual_castable": False}],
        identity={"classes": [{"class": "Class A", "level": 3, "subclass": None}],
                  "species": None},
    )
    assert "ritual-tag-mismatch" in _codes(sheet, access)


def test_invalid_secondary_cast(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a",
                 "secondary_cast": {"resource": "invalid_resource"}}],
    )
    assert "invalid-secondary-cast" in _codes(sheet, access)


def test_invalid_secondary_cast_missing_uses(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a",
                 "secondary_cast": {"resource": "slotless_per_rest", "uses": 0}}],
    )
    assert "invalid-secondary-cast" in _codes(sheet, access)


def test_valid_secondary_cast(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a",
                 "secondary_cast": {"resource": "spell_slot"}}],
    )
    assert "invalid-secondary-cast" not in _codes(sheet, access)


def test_smoke_all_checks_registered(access):
    cnames = [c.__module__.split(".")[-1] for c in ALL_CHECKS]
    assert "grimoire" in cnames
    assert "spellcasting" in cnames


def test_sources_missing_is_noop(access):
    sheet = _make_sheet()
    del sheet["sources"]
    assert check(sheet, access) == []


def test_malformed_identity_noop(access):
    sheet = _make_sheet(
        sources={"class:class-a": {"kind": "class", "ability": "a1", "modifier": 2,
                                   "save_dc": 12, "attack_bonus": 4}},
        spells=[{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "class:class-a"}],
        identity="not a dict",
    )
    assert isinstance(check(sheet, access), list)
