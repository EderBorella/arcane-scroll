"""Spellcasting domain: DC/attack-bonus math, per-class cantrip/prepared count ceilings, leveled/pact
slot tables, and spell-list membership. OUT of scope for this cluster (deferred, see F05-T20):
ritual-castability, the full per-source availability model, and Bard-Magical-Secrets-style list
widening.

Combined caster level (multiclass rule): full classes contribute their level, half classes contribute
`(level+1)//2` (round up), and third-caster subclasses contribute `level//3` (round down) -- this
project treats the round-up-for-half rule as book-grounded (see CLAUDE.md). Pact magic is always a
separate slot pool, never folded into the shared/multiclass slots. Slot comparisons check `max` only
(`used` is a play-state field, not a legality one). Cantrip/prepared counts are ceilings -- being
under is fine, a sheet may be mid-build. Every expectation is derived from the DB; malformed sheet
data becomes a structured finding rather than a raise."""
from access.validator import abilities as abilities_q
from access.validator import spellcasting as q
from validator.report import Violation

DOMAIN = "spellcasting"


def _ident(sheet: dict) -> dict:
    ident = sheet.get("identity", {}) or {}
    return ident if isinstance(ident, dict) else {}


def _classes(ident: dict) -> list:
    raw = ident.get("classes")
    return raw if isinstance(raw, list) else []


def _ability_final(access, abilities_sheet, ability_id: str | None) -> int | None:
    if ability_id is None or not isinstance(abilities_sheet, dict):
        return None
    for k, entry in abilities_sheet.items():
        if not isinstance(entry, dict):
            continue
        if abilities_q.ability_id(access, k) != ability_id:
            continue
        final = entry.get("final")
        if isinstance(final, int) and not isinstance(final, bool):
            return final
    return None


def _classify_casters(classes: list, access) -> tuple[list[dict], tuple[str, int] | None]:
    """(leveled, pact) -- `leveled` is [{"kind": "class"|"third", "cid"|"sid", "level", "prog"}, ...]
    for full/half classes and third-caster subclasses; `pact` is (class_id, level) for a pact class,
    or None. Unresolvable/malformed entries contribute nothing (never raise)."""
    leveled: list[dict] = []
    pact: tuple[str, int] | None = None
    for c in classes:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is not None:
            prog = q.caster_progression(access, cid)
            if prog in ("full", "half"):
                leveled.append({"kind": "class", "cid": cid, "level": level, "prog": prog})
            elif prog == "pact" and pact is None:
                pact = (cid, level)
        sub = c.get("subclass")
        if sub:
            sid = access.resolve("subclass", sub)
            if sid is not None and q.subclass_is_third_caster(access, sid):
                leveled.append({"kind": "third", "sid": sid, "level": level})
    return leveled, pact


def _combined_level(leveled: list[dict]) -> int:
    total = 0
    for entry in leveled:
        if entry["kind"] == "third":
            total += entry["level"] // 3
        elif entry["prog"] == "full":
            total += entry["level"]
        else:  # half
            total += (entry["level"] + 1) // 2
    return total


def _actual_slots(shared_slots) -> dict[int, int] | None:
    if not isinstance(shared_slots, dict):
        return None
    actual: dict[int, int] = {}
    for k, entry in shared_slots.items():
        try:
            lvl = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        mx = entry.get("max")
        if isinstance(mx, int) and not isinstance(mx, bool):
            actual[lvl] = mx
    return actual


def _check_dc_attack(sc: dict, sheet: dict, access, v: list[Violation]) -> None:
    ability_key = sc.get("ability")
    pb = sheet.get("proficiency_bonus")
    if ability_key is None or not (isinstance(pb, int) and not isinstance(pb, bool)):
        return
    aid = abilities_q.ability_id(access, ability_key)
    final = _ability_final(access, sheet.get("abilities"), aid)
    if aid is None or final is None:
        return
    mod = (final - 10) // 2

    save_dc = sc.get("save_dc")
    if isinstance(save_dc, int) and not isinstance(save_dc, bool):
        expected = 8 + pb + mod
        if save_dc != expected:
            v.append(Violation(DOMAIN, "spell-save-dc-mismatch", "illegal",
                               f"save_dc {save_dc} != expected {expected}", "spellcasting.save_dc"))

    attack_bonus = sc.get("attack_bonus")
    if isinstance(attack_bonus, int) and not isinstance(attack_bonus, bool):
        expected = pb + mod
        if attack_bonus != expected:
            v.append(Violation(DOMAIN, "spell-attack-mismatch", "illegal",
                               f"attack_bonus {attack_bonus} != expected {expected}",
                               "spellcasting.attack_bonus"))


def _check_shared_slots(sc: dict, leveled: list[dict], access, v: list[Violation]) -> None:
    actual = _actual_slots(sc.get("shared_slots"))
    if actual is None:
        return  # no slots declared (or malformed) -- nothing to compare, never raise

    if len(leveled) == 1:
        only = leveled[0]
        if only["kind"] == "class":
            expected = q.class_slots(access, only["cid"], only["level"])
        else:
            expected = q.subclass_slots(access, only["sid"], only["level"])
    elif len(leveled) > 1:
        expected = q.multiclass_slots(access, _combined_level(leveled))
    else:
        return  # no leveled caster on this sheet -- no baseline to compare against

    for lvl in sorted(set(actual) | set(expected)):
        if actual.get(lvl) != expected.get(lvl):
            v.append(Violation(DOMAIN, "spell-slots-mismatch", "illegal",
                               f"slot level {lvl}: expected max {expected.get(lvl)}, got {actual.get(lvl)}",
                               f"spellcasting.shared_slots.{lvl}"))


def _check_pact_slots(sc: dict, pact: tuple[str, int] | None, access, v: list[Violation]) -> None:
    pact_sheet = sc.get("pact_slots")
    if pact is None:
        if pact_sheet is not None:
            v.append(Violation(DOMAIN, "unexpected-pact-slots", "illegal",
                               "pact_slots present but no pact-caster class on this sheet",
                               "spellcasting.pact_slots"))
        return

    if not isinstance(pact_sheet, dict):
        return
    cid, level = pact
    lvl = pact_sheet.get("level")
    mx = pact_sheet.get("max")
    if not (isinstance(lvl, int) and not isinstance(lvl, bool)
            and isinstance(mx, int) and not isinstance(mx, bool)):
        return
    expected = q.pact_slots(access, cid, level)
    if expected.get(lvl) != mx:
        v.append(Violation(DOMAIN, "pact-slots-mismatch", "illegal",
                           f"pact slots: expected max {expected.get(lvl)} at level {lvl}, got {mx}",
                           "spellcasting.pact_slots"))


def _granted_spell_ids(sheet: dict, ident: dict, classes: list, access) -> set[str]:
    granted: set[str] = set()

    sp_id = access.resolve("species", ident.get("species"))
    if sp_id is not None:
        granted |= q.granted_spell_ids(access, "species", sp_id)

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            if isinstance(f, str):
                fname = f
            elif isinstance(f, dict):
                fname = f.get("name")
            else:
                continue
            fid = access.resolve("feat", fname)
            if fid is not None:
                granted |= q.granted_spell_ids(access, "feat", fid)

    for c in classes:
        if not isinstance(c, dict):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is not None:
            granted |= q.granted_spell_ids(access, "class", cid)
        sub = c.get("subclass")
        if sub:
            sid = access.resolve("subclass", sub)
            if sid is not None:
                granted |= q.granted_spell_ids(access, "subclass", sid)

    return granted


def _check_counts_and_list(sc: dict, ident: dict, classes: list, sheet: dict, access,
                           v: list[Violation]) -> None:
    granted = _granted_spell_ids(sheet, ident, classes, access)

    for key, entry in sc.items():
        cid = access.resolve("class", key)
        if cid is None:
            continue  # ability/save_dc/attack_bonus/shared_slots/pact_slots -- not a caster entry
        if not isinstance(entry, dict):
            continue
        path = f"spellcasting.{key}"

        cantrips = entry.get("cantrips")
        cantrips = cantrips if isinstance(cantrips, list) else []
        prepared = entry.get("prepared")
        prepared = prepared if isinstance(prepared, list) else []

        level = None
        for c in classes:
            if isinstance(c, dict) and access.resolve("class", c.get("class")) == cid:
                lvl = c.get("level")
                if isinstance(lvl, int) and not isinstance(lvl, bool):
                    level = lvl
                    break
        if level is not None:
            known, prepped = q.cantrips_prepared(access, cid, level)
            if known is not None and len(cantrips) > known:
                v.append(Violation(DOMAIN, "too-many-cantrips", "illegal",
                                   f"{key}: {len(cantrips)} cantrips exceeds the {known} known", path))
            if prepped is not None and len(prepared) > prepped:
                v.append(Violation(DOMAIN, "too-many-prepared", "illegal",
                                   f"{key}: {len(prepared)} prepared exceeds the {prepped} allowed", path))

        for name in list(cantrips) + list(prepared):
            sid = access.resolve("spell", name)
            if sid is None:
                v.append(Violation(DOMAIN, "unknown-spell", "illegal",
                                   f"unknown spell: {name!r}", path))
                continue
            if not q.spell_on_class_list(access, sid, cid) and sid not in granted:
                v.append(Violation(DOMAIN, "spell-not-on-list", "illegal",
                                   f"{name}: not on {key}'s spell list and not otherwise granted", path))


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    sc = sheet.get("spellcasting")
    if not isinstance(sc, dict):
        return v

    ident = _ident(sheet)
    classes = _classes(ident)
    leveled, pact = _classify_casters(classes, access)

    _check_dc_attack(sc, sheet, access, v)
    _check_shared_slots(sc, leveled, access, v)
    _check_pact_slots(sc, pact, access, v)
    _check_counts_and_list(sc, ident, classes, sheet, access, v)

    return v
