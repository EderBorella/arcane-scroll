"""Abilities domain: ability-key resolution, modifier consistency, the standard score cap, and
background-boost legality. Every expectation is derived from the DB."""
from access.validator import abilities as q
from validator.report import Violation

DOMAIN = "abilities"

_VALID_BOOST_SHAPES = ([1, 1, 1], [1, 2])


def _ability_caps(sheet: dict, access, base_cap: int | None) -> dict[str, int]:
    """Each ability's individual score ceiling, re-derived from the grant spine.

    The standard cap (``base_cap``) applies to every ability, then two DB-modelled exceptions raise
    a specific ability's ceiling above it: a class's level-20 capstone (which raises two fixed
    abilities' maximum), and an Epic-Boon feat (which raises the boosted ability's maximum). Each is
    read from ``grant_ability_increase`` — a fixed-target grant (``from_any`` False) raises its
    listed abilities; a choose-target grant (``from_any`` True, e.g. a boon boosting an ability of
    the player's choice) raises the ability the sheet records this feat as increasing. Nothing here
    reads the deriver: every ceiling comes from the DB, keyed to the build's own classes and feats."""
    if base_cap is None:
        return {}
    caps: dict[str, int] = {}

    def bump(aid: str | None, cap) -> None:
        if aid and isinstance(cap, int) and cap > caps.get(aid, base_cap):
            caps[aid] = cap

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        cid = access.resolve("class", c.get("class"))
        sub_id = access.resolve("subclass", c.get("subclass"))
        for owner_kind, owner_id in (("class", cid), ("subclass", sub_id)):
            if not owner_id:
                continue
            for g in q.ability_increase_caps(access, owner_kind, owner_id, at_level=level):
                # A class/subclass ceiling exception is a fixed-target grant naming the abilities it
                # raises; choose-target class grants (none modelled today) would need the build's own
                # choice, so they are left at the base cap here.
                if not g["from_any"]:
                    for aid in g["ability_ids"]:
                        bump(aid, g["cap"])

    for f in sheet.get("feats", []) or []:
        name = f.get("name") if isinstance(f, dict) else f
        fid = access.resolve("feat", name)
        if not fid:
            continue
        inc = f.get("ability_increase") if isinstance(f, dict) else None
        chosen_aid = q.ability_id(access, inc.get("ability")) if isinstance(inc, dict) else None
        for g in q.ability_increase_caps(access, "feat", fid):
            if g["from_any"]:
                # A boon that boosts an ability of the player's choice raises the ceiling of the
                # ability the sheet records this feat as increasing (constrained to the eligible pool
                # when the grant lists one).
                if chosen_aid and (not g["ability_ids"] or chosen_aid in g["ability_ids"]):
                    bump(chosen_aid, g["cap"])
            else:
                for aid in g["ability_ids"]:
                    bump(aid, g["cap"])
    return caps


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    abilities = sheet.get("abilities")
    if not isinstance(abilities, dict):
        v.append(Violation(DOMAIN, "malformed-abilities", "illegal",
                           "abilities must be a dict", "abilities"))
        return v

    base_cap = q.standard_ability_cap(access)
    caps = _ability_caps(sheet, access, base_cap)
    resolved: set[str] = set()
    boosts: list[tuple[int, str]] = []

    for k, entry in abilities.items():
        path = f"abilities.{k}"
        aid = q.ability_id(access, k)
        if aid is None:
            v.append(Violation(DOMAIN, "unknown-ability", "illegal",
                               f"unknown ability: {k!r}", path))
            continue
        resolved.add(aid)
        if not isinstance(entry, dict):
            continue

        final = entry.get("final")
        modifier = entry.get("modifier")
        final_ok = isinstance(final, int) and not isinstance(final, bool)
        modifier_ok = isinstance(modifier, int) and not isinstance(modifier, bool)
        # The modifier-mismatch rule needs both fields; a sheet shape that carries no per-ability
        # modifier (top-level-fields sheet) simply has nothing to cross-check here.
        if final_ok and modifier_ok:
            if modifier != (final - 10) // 2:
                v.append(Violation(DOMAIN, "modifier-mismatch", "illegal",
                                   f"{k}: modifier {modifier} does not match final score {final}", path))
        # The over-cap rule needs only the final score, so it must fire regardless of whether a
        # per-ability modifier is present -- otherwise an over-cap score on a sheet shape without
        # modifiers would validate as legal.
        per_cap = caps.get(aid, base_cap)
        if final_ok and per_cap is not None and final > per_cap:
            v.append(Violation(DOMAIN, "ability-over-cap", "illegal",
                               f"{k}: final score {final} exceeds the cap {per_cap} "
                               "(item-set exceptions are checked in the items domain)", path))

        bonus = entry.get("background_bonus")
        if bonus is not None:
            if isinstance(bonus, int) and not isinstance(bonus, bool):
                if bonus:
                    boosts.append((bonus, aid))
            else:
                v.append(Violation(DOMAIN, "background-bonus-malformed", "illegal",
                                   f"background_bonus must be an integer, got {bonus!r}", f"{path}.background_bonus"))

    missing = set(q.all_ability_ids(access)) - resolved
    if missing:
        v.append(Violation(DOMAIN, "missing-ability", "incomplete",
                           f"missing ability entries: {sorted(missing)}", "abilities"))

    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        ident = {}
    bg_id = access.resolve("background", ident.get("background"))
    if bg_id is not None:
        if not boosts:
            v.append(Violation(DOMAIN, "background-boost-missing", "incomplete",
                               "background ability boosts (total 3) are expected but none are declared",
                               "abilities"))
        else:
            allowed = set(q.background_boost_abilities(access, bg_id))
            bad_target = any(aid not in allowed for _, aid in boosts)
            values = sorted(b for b, _ in boosts)
            if bad_target or values not in _VALID_BOOST_SHAPES:
                v.append(Violation(DOMAIN, "background-boost-illegal", "illegal",
                                   "background ability boosts must total 3 points, as {2,1} or {1,1,1}, "
                                   "all on abilities the background allows", "abilities"))
    return v
