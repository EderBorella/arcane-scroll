"""Backstory helpers (the pure compute retained after the choice-grammar cutover): physical bounds
and appearance-palette selection, served from the reference DB via the generator access layer.
Deterministic against the synthetic rules DB."""
from app.generation import helpers as H


def test_physical_bounds_from_db(gen_access):
    assert H.physical_bounds(gen_access, "species-a") == ((16, 90), (58, 78), (110, 270))


def test_physical_bounds_default_fallback(gen_access):
    # species-l has no bounds row → the generic default
    assert H.physical_bounds(gen_access, "species-l") == ((16, 100), (48, 84), (80, 320))
    assert H.physical_bounds(gen_access, None) == ((16, 100), (48, 84), (80, 320))


def test_appearance_options_override_vs_default(gen_access):
    # species-v overrides the skin axis; species-a falls back to the default palette
    assert H.appearance_options(gen_access, "skin", "species-v") == ["Bronze", "Silver"]
    assert H.appearance_options(gen_access, "skin", "species-a") == ["Pale", "Tan", "Dark"]


def test_appearance_options_non_overridable_axis(gen_access):
    # gender is never overridden → the default palette regardless of species
    assert H.appearance_options(gen_access, "gender", "species-v") == ["Male", "Female", "Nonbinary"]
