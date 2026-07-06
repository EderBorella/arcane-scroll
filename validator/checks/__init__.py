"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
from validator.checks import abilities, identity, saving_throws

ALL_CHECKS = [identity.check, abilities.check, saving_throws.check]
