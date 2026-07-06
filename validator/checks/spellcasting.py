"""Spellcasting domain (V6 contract shape): per-source DC/attack math, class-source budget
truthfulness (a class source may not claim more than the class grants), spell counts vs. each
source's own declared budget, leveled/pact slot tables, spell-list membership, and (name, source)
uniqueness. OUT of scope for this cluster (deferred, see F05-T20): recovery<->bucket coupling and
ritual-castability.

Contract: `spellcasting` is `None` (no findings) or `{sources: {<id>: castingSource}, spell_slots?,
pact_slots?, spells: [{name, level, bucket, source, ...}]}`. `castingSource` carries its OWN
`modifier` (no ability-score lookup needed here) plus `save_dc`/`attack_bonus` and optional
`cantrips_known`/`prepared_limit` budgets. Combined caster level (multiclass rule): full classes
contribute their level, half classes contribute `(level+1)//2` (round up), third-caster subclasses
contribute `level//3` (round down). Pact magic is always a separate slot pool. Slot comparisons
check `max` only (`remaining` is play state, not a legality one). Cantrip/prepared counts are
ceilings -- being under is fine, a sheet may be mid-build. Every expectation is derived from the DB;
malformed sheet data becomes a structured finding (or is silently skipped) rather than a raise."""
from access.validator import spellcasting as q
from validator.report import Violation

DOMAIN = "spellcasting"


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _ident(sheet: dict) -> dict:
    ident = sheet.get("identity", {}) or {}
    return ident if isinstance(ident, dict) else {}


def _classes(ident: dict) -> list:
    raw = ident.get("classes")
    return raw if isinstance(raw, list) else []


def _level_for_class(classes: list, cid: str, access) -> int | None:
    for c in classes:
        if not isinstance(c, dict):
            continue
        if access.resolve("class", c.get("class")) == cid:
            level = c.get("level")
            if _int(level):
                return level
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
        if not _int(level):
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


def _slot_table(raw) -> dict[int, int] | None:
    """{slot_level: max} from a sheet slotTable, or None if absent/malformed."""
    if not isinstance(raw, dict):
        return None
    out: dict[int, int] = {}
    for k, entry in raw.items():
        try:
            lvl = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        mx = entry.get("max")
        if _int(mx):
            out[lvl] = mx
    return out


def _check_dc_attack(sources: dict, pb, v: list[Violation]) -> None:
    if not _int(pb):
        return
    for sid, src in sources.items():
        if not isinstance(src, dict):
            continue
        mod = src.get("modifier")
        if not _int(mod):
            continue
        path = f"spellcasting.sources.{sid}"

        save_dc = src.get("save_dc")
        if _int(save_dc):
            expected = 8 + pb + mod
            if save_dc != expected:
                v.append(Violation(DOMAIN, "spell-save-dc-mismatch", "illegal",
                                   f"{sid}: save_dc {save_dc} != expected {expected}", f"{path}.save_dc"))

        attack_bonus = src.get("attack_bonus")
        if _int(attack_bonus):
            expected = pb + mod
            if attack_bonus != expected:
                v.append(Violation(DOMAIN, "spell-attack-mismatch", "illegal",
                                   f"{sid}: attack_bonus {attack_bonus} != expected {expected}",
                                   f"{path}.attack_bonus"))


def _check_source_budget_truthfulness(sources: dict, classes: list, access,
                                      v: list[Violation]) -> None:
    for sid, src in sources.items():
        if not isinstance(src, dict):
            continue
        cid = access.resolve("class", sid)
        if cid is None:
            continue  # not a class source -- a feat/species/item grants a fixed set, no DB budget
        level = _level_for_class(classes, cid, access)
        if level is None:
            continue
        known, prepped = q.cantrips_prepared(access, cid, level)
        path = f"spellcasting.sources.{sid}"

        declared_known = src.get("cantrips_known")
        if known is not None and _int(declared_known) and declared_known > known:
            v.append(Violation(DOMAIN, "source-budget-too-high", "illegal",
                               f"{sid}: declares {declared_known} cantrips_known but the class grants "
                               f"only {known} at level {level}", f"{path}.cantrips_known"))

        declared_prepped = src.get("prepared_limit")
        if prepped is not None and _int(declared_prepped) and declared_prepped > prepped:
            v.append(Violation(DOMAIN, "source-budget-too-high", "illegal",
                               f"{sid}: declares {declared_prepped} prepared_limit but the class grants "
                               f"only {prepped} at level {level}", f"{path}.prepared_limit"))


def _check_spell_counts(sources: dict, spells: list, v: list[Violation]) -> None:
    cantrip_counts: dict[str, int] = {}
    prepared_counts: dict[str, int] = {}
    for entry in spells:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("source")
        bucket = entry.get("bucket")
        if bucket == "cantrip":
            cantrip_counts[sid] = cantrip_counts.get(sid, 0) + 1
        elif bucket == "prepared":
            prepared_counts[sid] = prepared_counts.get(sid, 0) + 1

    for sid, src in sources.items():
        if not isinstance(src, dict):
            continue
        path = f"spellcasting.sources.{sid}"

        budget = src.get("cantrips_known")
        count = cantrip_counts.get(sid, 0)
        if _int(budget) and count > budget:
            v.append(Violation(DOMAIN, "too-many-cantrips", "illegal",
                               f"{sid}: {count} cantrips exceeds the declared {budget} known", path))

        budget = src.get("prepared_limit")
        count = prepared_counts.get(sid, 0)
        if _int(budget) and count > budget:
            v.append(Violation(DOMAIN, "too-many-prepared", "illegal",
                               f"{sid}: {count} prepared exceeds the declared {budget} allowed", path))


def _check_slots(sc: dict, leveled: list[dict], pact: tuple[str, int] | None, access,
                 v: list[Violation]) -> None:
    actual = _slot_table(sc.get("spell_slots"))
    if actual is not None:
        if len(leveled) == 1:
            only = leveled[0]
            if only["kind"] == "class":
                expected = q.class_slots(access, only["cid"], only["level"])
            else:
                expected = q.subclass_slots(access, only["sid"], only["level"])
            for lvl in sorted(set(actual) | set(expected)):
                if actual.get(lvl) != expected.get(lvl):
                    v.append(Violation(DOMAIN, "spell-slots-mismatch", "illegal",
                                       f"slot level {lvl}: expected max {expected.get(lvl)}, got {actual.get(lvl)}",
                                       f"spellcasting.spell_slots.{lvl}"))
        elif len(leveled) > 1:
            expected = q.multiclass_slots(access, _combined_level(leveled))
            for lvl in sorted(set(actual) | set(expected)):
                if actual.get(lvl) != expected.get(lvl):
                    v.append(Violation(DOMAIN, "spell-slots-mismatch", "illegal",
                                       f"slot level {lvl}: expected max {expected.get(lvl)}, got {actual.get(lvl)}",
                                       f"spellcasting.spell_slots.{lvl}"))
        # len(leveled) == 0: no leveled-caster baseline to compare against -- never raise/flag

    pact_sheet = _slot_table(sc.get("pact_slots"))
    if pact is None:
        if pact_sheet is not None:
            v.append(Violation(DOMAIN, "unexpected-pact-slots", "illegal",
                               "pact_slots present but no pact-caster class on this sheet",
                               "spellcasting.pact_slots"))
        return
    if pact_sheet is None:
        return
    cid, level = pact
    expected = q.pact_slots(access, cid, level)
    for lvl in sorted(set(pact_sheet) | set(expected)):
        if pact_sheet.get(lvl) != expected.get(lvl):
            v.append(Violation(DOMAIN, "pact-slots-mismatch", "illegal",
                               f"pact slot level {lvl}: expected max {expected.get(lvl)}, got {pact_sheet.get(lvl)}",
                               f"spellcasting.pact_slots.{lvl}"))


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


def _check_spell_list_and_uniqueness(sheet: dict, ident: dict, classes: list, spells: list,
                                     access, v: list[Violation]) -> None:
    granted = _granted_spell_ids(sheet, ident, classes, access)
    seen: set[tuple] = set()

    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        path = f"spellcasting.spells[{i}]"
        name = entry.get("name")
        source = entry.get("source")
        bucket = entry.get("bucket")

        key = (name, source)
        if key in seen:
            v.append(Violation(DOMAIN, "spell-duplicate", "illegal",
                               f"duplicate spell {name!r} from source {source!r}", path))
        else:
            seen.add(key)

        sid_spell = access.resolve("spell", name)
        if sid_spell is None:
            v.append(Violation(DOMAIN, "unknown-spell", "illegal", f"unknown spell: {name!r}", path))
            continue

        if bucket == "always":
            continue  # a grant -- no class-list check

        cid = access.resolve("class", source)
        if cid is None:
            continue  # not a class source (feat/species/subclass/item) -- treat as granted, no list check
        if not q.spell_on_class_list(access, sid_spell, cid) and sid_spell not in granted:
            v.append(Violation(DOMAIN, "spell-not-on-list", "illegal",
                               f"{name}: not on {source}'s spell list and not otherwise granted", path))


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    sc = sheet.get("spellcasting")
    if sc is None or not isinstance(sc, dict):
        return v

    pb = sheet.get("proficiency_bonus")
    sources = sc.get("sources", {})
    sources = sources if isinstance(sources, dict) else {}
    spells = sc.get("spells", [])
    spells = spells if isinstance(spells, list) else []

    ident = _ident(sheet)
    classes = _classes(ident)
    leveled, pact = _classify_casters(classes, access)

    _check_dc_attack(sources, pb, v)
    _check_source_budget_truthfulness(sources, classes, access, v)
    _check_spell_counts(sources, spells, v)
    _check_slots(sc, leveled, pact, access, v)
    _check_spell_list_and_uniqueness(sheet, ident, classes, spells, access, v)

    return v
