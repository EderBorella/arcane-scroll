"""Layer: ability scores. A final score caps at 30 (Epic Boons), while the BACKGROUND increase can't
raise a score above 20; and the increases come from the character's background — landing only on the
background's three abilities, in a +2/+1 or +1/+1/+1 pattern. The granted increase is read from
`abilities[].background_bonus` (falling back to the legacy `racial_bonus`); feat/level ASIs are folded
into `final`, not here. Collects all findings; never raises."""
from validator.report import Violation

LAYER = "ability_scores"


def _bump(v):
    """The background-granted increase for an ability — the dedicated field, else the legacy one."""
    b = v.get("background_bonus")
    return (v.get("racial_bonus") or 0) if b is None else b


def check(sheet, rules):
    out = []
    abils = sheet.get("abilities") or {}
    for ab, v in abils.items():
        final = v.get("final")
        if final is not None and final > 30:
            out.append(Violation(LAYER, "ability_above_30", f"{ab} is {final}; the maximum is 30", 30, final))
        base, bump = v.get("base"), _bump(v)
        if base is not None and bump and base + bump > 20:
            out.append(Violation(LAYER, "background_increase_above_20",
                                 f"{ab} background increase raises {base}+{bump} above 20", 20, base + bump))

    bg = (sheet.get("identity") or {}).get("background")
    allowed = rules.background_abilities(bg)
    bumped = {ab: _bump(v) for ab, v in abils.items()}
    bumped = {ab: n for ab, n in bumped.items() if n}

    if allowed is None:
        if bumped:
            out.append(Violation(LAYER, "background_unrecognised",
                                 f"ability increases present but background {bg!r} isn't a known background",
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
