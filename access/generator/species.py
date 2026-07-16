"""Species-domain option reads for the choice grammar: the species catalogue the grammar picks from,
plus the trait, size, and creature-type facts the CORE deriver reads once a species is chosen. Pure
DB reads — no rule math."""
from access.generator import GeneratorAccess


def list_species(access: GeneratorAccess) -> list:
    """Every species the grammar may choose, as (id, name, creature_type_id, base_walk_speed) rows,
    ordered by id."""
    return access.db.q(
        "SELECT id, name, creature_type_id, base_walk_speed FROM species ORDER BY id")


def species_traits(access: GeneratorAccess, species_id: str) -> list:
    """A species's named traits, as (id, species_id, ordinal, name) rows in the species's declared
    ordinal order (then id, for a stable tie-break)."""
    return access.db.q(
        "SELECT id, species_id, ordinal, name FROM species_trait WHERE species_id=? "
        "ORDER BY ordinal, id", species_id)


def species_sizes(access: GeneratorAccess, species_id: str) -> list[str]:
    """The size ids a species may be (a species can offer more than one), ordered by size_id.
    Empty if the species is unknown or declares no size."""
    return [r["size_id"] for r in access.db.q(
        "SELECT size_id FROM species_size WHERE species_id=? ORDER BY size_id", species_id)]


def species_creature_type(access: GeneratorAccess, species_id: str) -> str | None:
    """The creature-type id of a species, or None if the species is unknown."""
    return access.db.scalar("SELECT creature_type_id FROM species WHERE id=?", species_id)
