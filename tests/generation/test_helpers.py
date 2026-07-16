"""Backstory/name helpers (the pure compute retained after the choice-grammar cutover): physical
bounds and skin palette, matched casing/punctuation-tolerantly. Deterministic against the synthetic
catalog."""
from app.generation import helpers as H


def test_skin_options(catalog):
    assert H.skin_options(catalog, "Scaled") == ["Bronze", "Silver"]          # origin override
    assert H.skin_options(catalog, "Human") == catalog.get("skin_default")    # default palette


def test_flavour_lookups_tolerate_casing(catalog):
    # race_phys/skin_overrides are keyed by display name; a differently-cased key (as the /backstory
    # path may pass) must still resolve, not silently fall back to generic defaults
    human = (tuple([16, 90]), tuple([58, 78]), tuple([110, 270]))
    assert H.physical_bounds(catalog, "human") == human
    assert H.physical_bounds(catalog, "HUMAN") == human
    assert H.skin_options(catalog, "scaled") == ["Bronze", "Silver"]
