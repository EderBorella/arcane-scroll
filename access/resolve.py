"""Display-name -> id resolution over the reference DB's own name columns.

Sheets carry display names ("Class A", "Sub A"); the DB keys on slug ids ("class-a", "sub-a").
This maps one to the other per dimension, lazily and cached. Content-neutral: the names live in the
DB as data — only the dim *table names* (structure) appear here, allow-listed."""
import re

from access.db import RulesDB

# dim tables with (id, name) the resolver may map — structure, not content
_DIMS = {
    "ability", "alignment", "armor_category", "background", "class", "condition", "creature_type",
    "damage_type", "feat", "language", "lineage", "movement_mode", "rarity", "school", "sense",
    "size", "skill", "species", "spell", "subclass", "tool", "tool_category", "weapon_property_vocab",
    "catalog_item", "class_feature", "subclass_feature", "class_option", "class_resource", "creature",
    "weapon_tier",
    "detail_option", "hazard", "mastery_property", "power", "species_trait",
}


def _norm(s: object) -> str:
    s = re.sub(r"\s*\([^)]*\)", "", str(s or ""))     # drop "(… qualifier)" noise
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


class Resolver:
    """Name->id resolver. `resolve(dim, name)` returns the id, or None if unknown."""

    def __init__(self, db: RulesDB):
        self._db = db
        self._maps: dict[str, dict[str, str]] = {}

    def _map(self, dim: str) -> dict[str, str]:
        if dim not in _DIMS:
            raise ValueError(f"resolver: unknown dimension {dim!r}")
        m = self._maps.get(dim)
        if m is None:
            m = {_norm(row["name"]): row["id"] for row in self._db.q(f"SELECT id, name FROM {dim}")}
            self._maps[dim] = m
        return m

    def resolve(self, dim: str, name: str | None) -> str | None:
        if name is None:
            return None
        return self._map(dim).get(_norm(name))
