"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
from validator.checks import abilities, defenses, feats, features, grimoire, identity, inventory, movement, proficiencies, proficiencies_equip, saving_throws, senses, spellcasting, vitals, weapon_mastery

ALL_CHECKS = [identity.check, abilities.check, saving_throws.check, vitals.check, proficiencies.check,
              proficiencies_equip.check, feats.check, spellcasting.check, grimoire.check, senses.check, movement.check, defenses.check, features.check,
              weapon_mastery.check]
# inventory.check is NOT in ALL_CHECKS — the inventory validator is inventory:1-specific via
# POST /validate-inventory; v10 sheets have their own equipped key and would produce false positives.
