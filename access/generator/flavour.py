"""Flavour-domain option reads for the backstory generator: a species's physical bounds (age /
height / weight), the appearance palettes (gender / eyes / hair / skin, with per-species overrides),
the seed story angles, and the flavour system prompt. Pure DB reads — no rule math (the schema
bounding, the override-vs-default choice, and the physical clamp belong to the generation helpers)."""
from access.generator import GeneratorAccess


def physical_bounds(access: GeneratorAccess, species_id: str | None) -> dict | None:
    """A species's physical bounds as a row (age_min/max, height_min/max, weight_min/max), or None
    when the species has no bounds row — the caller then applies its generic default."""
    if species_id is None:
        return None
    return access.db.one(
        "SELECT age_min, age_max, height_min, height_max, weight_min, weight_max "
        "FROM species_physical_bounds WHERE species_id=?", species_id)


def appearance_defaults(access: GeneratorAccess, axis: str) -> list[str]:
    """The shared default palette for an appearance axis (gender/eyes/hair/skin), ordered by ordinal.
    These are the species-agnostic rows (species_id IS NULL)."""
    return [r["value"] for r in access.db.q(
        "SELECT value FROM appearance_option WHERE axis=? AND species_id IS NULL "
        "ORDER BY ordinal", axis)]


def appearance_overrides(access: GeneratorAccess, axis: str, species_id: str | None) -> list[str]:
    """A species's override palette for an appearance axis, ordered by ordinal. Empty when the species
    has no override on the axis — the caller then falls back to the default palette."""
    if species_id is None:
        return []
    return [r["value"] for r in access.db.q(
        "SELECT value FROM appearance_option WHERE axis=? AND species_id=? "
        "ORDER BY ordinal", axis, species_id)]


def story_archetypes(access: GeneratorAccess) -> list[str]:
    """The seed story angles a backstory draws from when a request carries no unique hint, ordered by
    ordinal."""
    return [r["text"] for r in access.db.q(
        "SELECT text FROM story_archetype ORDER BY ordinal")]


def generator_prompt(access: GeneratorAccess, locator: str) -> str | None:
    """The generator prompt text for a locator (e.g. 'flavour_sys'), or None if none is stored."""
    return access.db.scalar("SELECT text FROM generator_prompt WHERE locator=?", locator)
