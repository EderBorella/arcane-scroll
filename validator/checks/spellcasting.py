"""Layer: spellcasting (2024). Two clean checks to start: leveled spells use the unified *prepared*
model (a leveled spell that isn't prepared is a 2014 'known-caster' artefact), and every spell must be
a real 2024 spell (present on some class's list). Count / per-class-list / slot checks come in later
increments. Collects all findings; never raises."""
from validator.report import Violation

LAYER = "spellcasting"


def check(sheet, rules):
    out = []
    cb = sheet.get("spellcasting")
    if not cb:
        return out
    known = rules.all_spells()      # empty if no spell-list data → membership check is skipped
    for s in cb.get("spells") or []:
        name, lvl, prepared = s.get("name"), s.get("level") or 0, s.get("prepared")
        if lvl >= 1 and prepared is False:
            out.append(Violation(LAYER, "spell_not_prepared",
                                 f"leveled spell '{name}' is not prepared; 2024 casters use one prepared list",
                                 True, prepared))
        if known and name not in known:
            out.append(Violation(LAYER, "unknown_spell",
                                 f"'{name}' is not on any 2024 class spell list", None, name))
    return out
