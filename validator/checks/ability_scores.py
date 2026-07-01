"""Layer: ability scores (2024). No final score above 20; and the ability-score **increases** come
from the character's BACKGROUND — landing only on the background's three abilities, in a +2/+1 or
+1/+1/+1 pattern. The granted increase is read from `abilities[].racial_bonus` on the sheet (feat/level
ASIs are folded into `final`, not here). Collects all findings; never raises."""
from validator.report import Violation

LAYER = "ability_scores"


def check(sheet, rules):
    out = []
    abils = sheet.get("abilities") or {}
    for ab, v in abils.items():
        final = v.get("final")
        if final is not None and final > 20:
            out.append(Violation(LAYER, "ability_above_20", f"{ab} is {final}; the maximum is 20", 20, final))

    bg = (sheet.get("identity") or {}).get("background")
    allowed = rules.background_abilities(bg)
    bumped = {ab: (v.get("racial_bonus") or 0) for ab, v in abils.items()}
    bumped = {ab: n for ab, n in bumped.items() if n}

    if allowed is None:
        if bumped:
            out.append(Violation(LAYER, "background_unrecognised",
                                 f"ability increases present but background {bg!r} isn't a known 2024 background",
                                 None, bg))
        return out

    stray = sorted(set(bumped) - set(allowed))
    if stray:
        out.append(Violation(LAYER, "asi_off_background",
                             f"ability increase on {stray} not granted by background '{bg}' (allows {allowed})",
                             allowed, sorted(bumped)))
    if not bumped:
        out.append(Violation(LAYER, "asi_missing",
                             f"no background ability increase; '{bg}' grants +2/+1 or +1/+1/+1 among {allowed}",
                             allowed, None))
    else:
        pattern = sorted(bumped.values(), reverse=True)
        if pattern not in ([2, 1], [1, 1, 1]):
            out.append(Violation(LAYER, "asi_pattern",
                                 f"ability-increase pattern {pattern} is not +2/+1 or +1/+1/+1",
                                 "[2, 1] or [1, 1, 1]", pattern))
    return out
