"""The generator's DAL query surface — one feature-access package per consumer, mirroring
``access/validator``. ``GeneratorAccess`` bundles a read-only DB handle and the name resolver;
per-domain query modules (species, classes, backgrounds, feats, spells, equipment) hold the
option/enumeration reads the choice grammar and the CORE deriver consume.

Where the validator asks "is this ONE chosen thing legal?", the generator asks "what MAY be chosen?"
— so these modules enumerate the option space (list every species/class/background, a class's
subclasses and skill pool, a caster's spell pool, an owner's starting-equipment options). Pure DB
reads only: no rule math (that belongs to the grammar and the deriver) and no writes."""
from access.db import RulesDB
from access.resolve import Resolver


class GeneratorAccess:
    def __init__(self, db: RulesDB | None = None, path: str | None = None):
        self.db = db or RulesDB(path)
        self.resolver = Resolver(self.db)

    def resolve(self, dim: str, name: str | None) -> str | None:
        return self.resolver.resolve(dim, name)
