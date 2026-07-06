"""The validator's DAL query surface — one feature-access package per consumer (S01). `ValidatorAccess`
bundles a read-only DB handle and the name resolver; per-domain query modules (identity, …) hold the
DB-fact queries the checks consume. No rule math here."""
from access.db import RulesDB
from access.resolve import Resolver


class ValidatorAccess:
    def __init__(self, db: RulesDB | None = None, path: str | None = None):
        self.db = db or RulesDB(path)
        self.resolver = Resolver(self.db)

    def resolve(self, dim: str, name: str | None) -> str | None:
        return self.resolver.resolve(dim, name)
