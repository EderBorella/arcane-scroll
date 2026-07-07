"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
from validator.checks import abilities, defenses, feats, features, identity, movement, proficiencies, saving_throws, senses, spellcasting, vitals

ALL_CHECKS = [identity.check, abilities.check, saving_throws.check, vitals.check, proficiencies.check,
              feats.check, spellcasting.check, senses.check, movement.check, defenses.check, features.check]
