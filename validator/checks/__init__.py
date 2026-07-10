"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
from validator.checks import abilities, defenses, feats, features, grimoire, identity, movement, proficiencies, proficiencies_equip, saving_throws, senses, spellcasting, vitals, weapon_mastery

ALL_CHECKS = [identity.check, abilities.check, saving_throws.check, vitals.check, proficiencies.check,
              proficiencies_equip.check, feats.check, spellcasting.check, grimoire.check, senses.check, movement.check, defenses.check, features.check,
              weapon_mastery.check]
