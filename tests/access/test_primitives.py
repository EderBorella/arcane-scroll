"""Sanity tests for the retrieval primitives (against the synthetic rules DB)."""
import pytest

from access import primitives as p


def test_grants_for_returns_owner_headers(db):
    rows = p.grants_for(db, "grant_proficiency", "species", "src-a")
    assert {r["id"] for r in rows} == {"gp1", "gp2"}


def test_grants_for_level_cap(db):
    # gp2 is gained at level 5; at level 1 only gp1 applies
    rows = p.grants_for(db, "grant_proficiency", "species", "src-a", at_level=1)
    assert {r["id"] for r in rows} == {"gp1"}


def test_grants_for_unknown_table_raises(db):
    with pytest.raises(ValueError):
        p.grants_for(db, "grant_nonsense", "species", "src-a")


def test_children_of_resolves_values(db):
    kids = p.children_of(db, "grant_proficiency", "gp1")
    assert [r["target_id"] for r in kids["grant_proficiency_value"]] == ["skill-x"]
    # gp1 has no category / weapon-filter children
    assert kids["grant_proficiency_category"] == []


def test_fixed_spell_ids_deterministic_order(db):
    # child rows were inserted (sp-b, sp-a); the reader orders by spell_id for a
    # rebuild-stable result
    assert p.fixed_spell_ids(db, "gsf1") == ["sp-a", "sp-b"]


def test_fixed_spell_ids_empty_for_unknown_grant(db):
    assert p.fixed_spell_ids(db, "no-such-grant") == []


def test_all_grants_for_fans_out(db):
    grants = p.all_grants_for(db, "species", "src-a")
    assert set(grants) == {"grant_proficiency", "grant_resistance"}
    assert "grant_bonus" not in grants  # that belongs to item-a, a different owner


def test_all_grants_for_level_cap(db):
    grants = p.all_grants_for(db, "species", "src-a", at_level=1)
    assert {r["id"] for r in grants["grant_proficiency"]} == {"gp1"}


def test_resource_at_takes_highest_row_at_or_below(db):
    assert p.resource_at(db, "res-a", 7)["count"] == 3   # level-5 row
    assert p.resource_at(db, "res-a", 1)["count"] == 2
    assert p.resource_at(db, "res-a", 0) is None


def test_sum_bonuses_totals_stacking_rows(db):
    assert p.sum_bonuses(db, "magic", "item-a", "ac") == 3
    assert p.sum_bonuses(db, "magic", "item-a", "nonexistent") == 0


def test_features_at(db):
    names = [r["name"] for r in p.features_at(db, class_id="cls-a", level=3)]
    assert names == ["FeatureA", "FeatureB"]   # FeatureC is level 5


def test_features_at_needs_an_owner(db):
    with pytest.raises(ValueError):
        p.features_at(db, level=3)


def test_constant(db):
    assert p.constant(db, "const-a") == 27
    assert p.constant(db, "missing") is None


def test_exists(db):
    assert p.exists(db, "class_feature", "cf-1") is True
    assert p.exists(db, "class_feature", "nope") is False


def test_exists_rejects_unlisted_table(db):
    with pytest.raises(ValueError):
        p.exists(db, "rules_constant", "const-a")


# ── item_grants_for: stowed non-attunement items confer nothing (F05-T138) ────
# A non-attunement magic item confers its passive grants only while EQUIPPED
# (mirroring the deriver's passive-on-equip branch). The same item stowed in the
# backpack must yield NO rows, or the walker over-includes and false-flags a
# grant the deriver never materialised. 'Item Passive' (mi-passive) is a
# non-attunement item owning one grant_sense row.

def test_item_grants_for_skips_stowed_non_attunement_item(db):
    sheet = {"backpack": [{"magic": True, "name": "Item Passive"}]}
    assert p.item_grants_for(db, sheet, "grant_sense", None) == []


def test_item_grants_for_includes_equipped_non_attunement_item(db):
    sheet = {"equipped": {"head": {"magic": True, "name": "Item Passive"}}}
    rows = p.item_grants_for(db, sheet, "grant_sense", None)
    assert {r["id"] for r in rows} == {"gs-mi-passive"}


def test_item_grants_for_attunement_gate_unchanged_when_stowed(db):
    # An ATTUNEMENT item ('Item Attune', mi-attune) confers its grants whenever
    # attuned, regardless of equipped/stowed location — the attunement gate is
    # untouched by the non-attunement location fix.
    stowed = {"backpack": [{"magic": True, "name": "Item Attune",
                            "attunement": {"attuned": True}}]}
    rows = p.item_grants_for(db, stowed, "grant_sense", None)
    assert {r["id"] for r in rows} == {"gs-mi-attune"}
    # ...and an un-attuned attunement item still confers nothing.
    unattuned = {"backpack": [{"magic": True, "name": "Item Attune"}]}
    assert p.item_grants_for(db, unattuned, "grant_sense", None) == []
