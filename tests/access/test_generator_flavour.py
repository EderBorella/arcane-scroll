"""Access-layer tests for the generator's flavour-domain reads (F05-T90): per-species physical
bounds, appearance palettes (default + per-species override), seed story angles, and the flavour
prompt. Exercised against the synthetic content-neutral rules DB (`gen_access`). Pure-read machinery
tests — no rule math."""
from access.generator import flavour


# --- physical bounds -------------------------------------------------------

def test_physical_bounds_row(gen_access):
    row = flavour.physical_bounds(gen_access, "species-a")
    assert (row["age_min"], row["age_max"]) == (16, 90)
    assert (row["height_min"], row["height_max"]) == (58, 78)
    assert (row["weight_min"], row["weight_max"]) == (110, 270)


def test_physical_bounds_unknown_species_is_none(gen_access):
    # species-l has no bounds row -> None (the caller falls back to a generic default)
    assert flavour.physical_bounds(gen_access, "species-l") is None
    assert flavour.physical_bounds(gen_access, "nope") is None
    assert flavour.physical_bounds(gen_access, None) is None


# --- appearance palettes ---------------------------------------------------

def test_appearance_defaults_ordered(gen_access):
    assert flavour.appearance_defaults(gen_access, "gender") == ["Male", "Female", "Nonbinary"]
    assert flavour.appearance_defaults(gen_access, "skin") == ["Pale", "Tan", "Dark"]


def test_appearance_overrides_present(gen_access):
    # species-v overrides the skin axis
    assert flavour.appearance_overrides(gen_access, "skin", "species-v") == ["Bronze", "Silver"]


def test_appearance_overrides_absent_is_empty(gen_access):
    # species-a has no skin override; gender never overrides; unknown/None -> empty
    assert flavour.appearance_overrides(gen_access, "skin", "species-a") == []
    assert flavour.appearance_overrides(gen_access, "gender", "species-v") == []
    assert flavour.appearance_overrides(gen_access, "skin", "nope") == []
    assert flavour.appearance_overrides(gen_access, "skin", None) == []


# --- story angles ----------------------------------------------------------

def test_story_archetypes_ordered(gen_access):
    rows = flavour.story_archetypes(gen_access)
    assert rows == ["Frame them through a mundane trade.", "Bond them to a place, not a person."]


# --- prompt ----------------------------------------------------------------

def test_generator_prompt(gen_access):
    assert flavour.generator_prompt(gen_access, "flavour_sys") == "TEST FLAVOUR PROMPT"
    assert flavour.generator_prompt(gen_access, "nope") is None
