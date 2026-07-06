"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
from validator.checks import abilities, feats, identity, proficiencies, saving_throws, spellcasting, vitals

ALL_CHECKS = [identity.check, abilities.check, saving_throws.check, vitals.check, proficiencies.check,
              feats.check, spellcasting.check]
