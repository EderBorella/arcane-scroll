"""CORE validator — validates a ``core-sheet:1`` against the DB grant spine.

All CORE-relevant checks from the existing validator suite are reused via a thin
path adapter that maps ``core-sheet:1`` field names to the v10-compatible names
the checks expect.  Spellcasting is excluded (it lives in GRIMOIRE).  MODIFIER‐only
fields (modifier, reduction, remaining) are absent in CORE and are skipped
gracefully by the existing checks.
"""
from validator.checks import (abilities, defenses, feats, features, identity,
                               movement, proficiencies, proficiencies_equip,
                               resources, saving_throws, senses, vitals,
                               weapon_mastery)
from validator.report import Violation, build_report

CORE_CHECKS = [identity.check, abilities.check, saving_throws.check, vitals.check,
               proficiencies.check, proficiencies_equip.check, feats.check,
               senses.check, movement.check, defenses.check, features.check,
               weapon_mastery.check, resources.check]


def adapt_core_to_v10(core_sheet: dict) -> dict:
    """Translate ``core-sheet:1`` field paths to v10-compatible paths.

    The existing checks were written against the v10 contract.  This adapter
    makes a shallow copy and remaps the few fields whose paths changed:

    ======================= ====================
    core-sheet:1            v10 (checks expect)
    ======================= ====================
    ``permanent_senses``    ``senses``
    ``permanent_defenses``  ``defenses``
    ``permanent_speed``     ``combat.speed``
    ``hit_points``          ``combat.hit_points``
    ``hit_dice``            ``combat.hit_dice``
    ======================= ====================

    All other fields (identity, abilities, saving_throws, skills, proficiencies,
    languages, weapon_masteries, features, feats, companions, permanent_effects,
    flavour) share the same path and structure in both contracts.
    """
    v10 = dict(core_sheet)

    # --- senses ---
    if "permanent_senses" in v10:
        v10["senses"] = v10.pop("permanent_senses")

    # --- defenses ---
    if "permanent_defenses" in v10:
        v10["defenses"] = v10.pop("permanent_defenses")

    # --- speed ---
    if "permanent_speed" in v10:
        perm_speed = v10.pop("permanent_speed")
        combat = v10.setdefault("combat", {})
        combat["speed"] = perm_speed

    # --- hit points & hit dice ---
    combat = v10.get("combat", {}) or {}
    if isinstance(combat, dict):
        pass
    else:
        combat = {}
    if "hit_points" in v10 and isinstance(v10["hit_points"], dict):
        combat["hit_points"] = v10.pop("hit_points")
    if "hit_dice" in v10 and isinstance(v10["hit_dice"], dict):
        combat["hit_dice"] = v10.pop("hit_dice")
    if combat:
        v10.setdefault("combat", {}).update(combat)
    elif "combat" not in v10:
        v10.pop("combat", None)

    return v10


def validate_core(sheet: dict, access) -> dict:
    """Validate a ``core-sheet:1`` dict against the reference DB.

    Returns a report dict with ``legal``, ``complete``, ``violations``, and
    ``summary`` keys (same shape as the full-sheet ``/validate`` endpoint).
    """
    v10 = adapt_core_to_v10(sheet)
    all_violations: list[Violation] = []

    for check in CORE_CHECKS:
        domain = getattr(check, "__module__", "").rsplit(".", 1)[-1]
        try:
            all_violations.extend(check(v10, access) or [])
        except Exception as exc:
            all_violations.append(
                Violation(domain or "core", "internal",
                          "internal",
                          f"check raised: {exc}",
                          None))
    return build_report(all_violations)
