"""Grimoire validation adapter — merges CORE + GRIMOIRE into a single dict and runs the grimoire
check module. No path translation needed: the grimoire check produces paths directly into the
grimoire:1 shape."""
from validator.checks import grimoire
from validator.report import Violation, build_report


def _merge_for_grimoire_check(core: dict, grimoire_sheet: dict) -> dict:
    return {
        "identity": core.get("identity", {}),
        "feats": core.get("feats", []),
        "features": core.get("features", []),
        "proficiency_bonus": core.get("proficiency_bonus"),
        "sources": grimoire_sheet.get("sources", {}),
        "spells": grimoire_sheet.get("spells", []),
        "spell_slots": grimoire_sheet.get("spell_slots"),
        "pact_slots": grimoire_sheet.get("pact_slots"),
    }


def validate_grimoire(core: dict, grimoire_sheet: dict, access) -> dict:
    merged = _merge_for_grimoire_check(core, grimoire_sheet)
    try:
        violations = grimoire.check(merged, access)
    except Exception as exc:
        violations = [Violation(kind="internal", domain="grimoire",
                                code="internal-error",
                                message=f"check raised: {exc}", path=None)]
    return build_report(violations)
