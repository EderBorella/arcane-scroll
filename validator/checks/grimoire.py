"""Grimoire domain (grimoire:1 shape): validates a merged CORE+GRIMOIRE dict against the DB.
Ports the 11 violations from spellcasting.py (adapted paths) and adds 5 new grimoire-specific
violations for a total of 16.

The check reads top-level keys ``sources``, ``spells``, ``spell_slots``, ``pact_slots`` (merged by
the adapter) and CORE fields ``identity``, ``feats``, ``proficiency_bonus``. Violation paths point
directly into the grimoire:1 shape (e.g. ``sources.class-a.save_dc``, ``spells[3]``).

Source-key format: ``{kind}:{db_id}`` (e.g. ``class:class-a``)."""
from access.validator import spellcasting as q
from validator.report import Violation

DOMAIN = "grimoire"

VALID_OWNER_KINDS = {"class", "subclass", "feat", "species", "lineage"}
VALID_RECOVERY = {"at_will", "spell_slot", "pact_slot", "slotless_per_rest", "ritual_only"}
VALID_SECONDARY_RESOURCES = {"spell_slot", "slotless_per_rest"}


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


def _subclass_for_class(classes: list, cid: str, access) -> str | None:
    for c in classes:
        if not isinstance(c, dict):
            continue
        if access.resolve("class", c.get("class")) == cid:
            return c.get("subclass")
    return None


def _classify_casters(classes: list, access) -> tuple[list[dict], tuple[str, int] | None]:
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
        else:
            total += (entry["level"] + 1) // 2
    return total


def _slot_table(raw) -> dict[int, int] | None:
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


def _parse_source_key(key: str) -> tuple[str, str] | None:
    if not isinstance(key, str) or ":" not in key:
        return None
    kind, oid = key.split(":", 1)
    if kind not in VALID_OWNER_KINDS:
        return None
    return kind, oid


# ── ported checks ────────────────────────────────────────────────────────────


def _check_dc_attack(sources: dict, pb, v: list[Violation]) -> None:
    if not _int(pb):
        return
    for sid, src in sources.items():
        if not isinstance(src, dict):
            continue
        mod = src.get("modifier")
        ability_mode = src.get("ability_mode")
        if ability_mode in ("fixed", "none"):
            mod = None
        if not _int(mod):
            continue
        path = f"sources.{sid}"

        save_dc = src.get("save_dc")
        if _int(save_dc):
            expected = 8 + pb + mod
            if save_dc != expected:
                v.append(Violation(DOMAIN, "spell-save-dc-mismatch", "illegal",
                                   f"{sid}: save_dc {save_dc} != expected {expected}",
                                   f"{path}.save_dc"))

        attack_bonus = src.get("attack_bonus")
        if _int(attack_bonus):
            expected = pb + mod
            if attack_bonus != expected:
                v.append(Violation(DOMAIN, "spell-attack-mismatch", "illegal",
                                   f"{sid}: attack_bonus {attack_bonus} != expected {expected}",
                                   f"{path}.attack_bonus"))


def _check_source_budget_truthfulness(sources: dict, classes: list, access,
                                      v: list[Violation]) -> None:
    for source_key, src in sources.items():
        if not isinstance(src, dict):
            continue
        parsed = _parse_source_key(source_key)
        if parsed is None or parsed[0] != "class":
            continue
        cid = parsed[1]
        level = _level_for_class(classes, cid, access)
        if level is None:
            continue
        known, prepped = q.cantrips_prepared(access, cid, level)
        path = f"sources.{source_key}"

        declared_known = src.get("cantrips_known")
        if known is not None and _int(declared_known) and declared_known > known:
            v.append(Violation(DOMAIN, "source-budget-too-high", "illegal",
                               f"{source_key}: declares {declared_known} cantrips_known but the "
                               f"class grants only {known} at level {level}",
                               f"{path}.cantrips_known"))

        declared_prepped = src.get("prepared_limit")
        if prepped is not None and _int(declared_prepped) and declared_prepped > prepped:
            v.append(Violation(DOMAIN, "source-budget-too-high", "illegal",
                               f"{source_key}: declares {declared_prepped} prepared_limit but the "
                               f"class grants only {prepped} at level {level}",
                               f"{path}.prepared_limit"))


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
        path = f"sources.{sid}"

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


def _check_pact_spells_known(sources: dict, spells: list, classes: list, access,
                             v: list[Violation]) -> None:
    """Independently enforce a pact-caster's spells-known count from the DB progression.

    A pact caster's spells-known limit lives in the same per-level progression as a prepared
    caster's prepared count (``class_cantrips_prepared.prepared_spells``).  The generic count
    check keys off the sheet's declared ``prepared_limit``, which a pact source has historically
    left unset (uncapped); this check re-derives the limit straight from the DB and flags a source
    whose placed prepared spells exceed it, so the count is enforced regardless of what the sheet
    declares."""
    prepared_counts: dict[str, int] = {}
    for entry in spells:
        if not isinstance(entry, dict):
            continue
        if entry.get("bucket") == "prepared":
            src = entry.get("source")
            prepared_counts[src] = prepared_counts.get(src, 0) + 1

    for source_key, src in sources.items():
        if not isinstance(src, dict):
            continue
        parsed = _parse_source_key(source_key)
        if parsed is None or parsed[0] != "class":
            continue
        cid = parsed[1]
        if q.caster_progression(access, cid) != "pact":
            continue
        level = _level_for_class(classes, cid, access)
        if level is None:
            continue
        _known, spells_known = q.cantrips_prepared(access, cid, level)
        if spells_known is None:
            continue
        count = prepared_counts.get(source_key, 0)
        if count > spells_known:
            v.append(Violation(DOMAIN, "too-many-prepared", "illegal",
                               f"{source_key}: {count} prepared exceeds the pact spells-known "
                               f"count {spells_known} at level {level}",
                               f"sources.{source_key}"))


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
                                       f"slot level {lvl}: expected max {expected.get(lvl)}, "
                                       f"got {actual.get(lvl)}",
                                       f"spell_slots.{lvl}"))
        elif len(leveled) > 1:
            expected = q.multiclass_slots(access, _combined_level(leveled))
            for lvl in sorted(set(actual) | set(expected)):
                if actual.get(lvl) != expected.get(lvl):
                    v.append(Violation(DOMAIN, "spell-slots-mismatch", "illegal",
                                       f"slot level {lvl}: expected max {expected.get(lvl)}, "
                                       f"got {actual.get(lvl)}",
                                       f"spell_slots.{lvl}"))

    pact_sheet = _slot_table(sc.get("pact_slots"))
    if pact is None:
        if pact_sheet is not None:
            v.append(Violation(DOMAIN, "unexpected-pact-slots", "illegal",
                               "pact_slots present but no pact-caster class on this sheet",
                               "pact_slots"))
        return
    if pact_sheet is None:
        return
    cid, level = pact
    expected = q.pact_slots(access, cid, level)
    for lvl in sorted(set(pact_sheet) | set(expected)):
        if pact_sheet.get(lvl) != expected.get(lvl):
            v.append(Violation(DOMAIN, "pact-slots-mismatch", "illegal",
                               f"pact slot level {lvl}: expected max {expected.get(lvl)}, "
                               f"got {pact_sheet.get(lvl)}",
                               f"pact_slots.{lvl}"))


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


def _effective_list_class(cid: str, classes: list, access) -> str:
    for c in classes:
        if not isinstance(c, dict):
            continue
        if access.resolve("class", c.get("class")) != cid:
            continue
        sub = c.get("subclass")
        if not sub:
            continue
        sid = access.resolve("subclass", sub)
        if sid is None:
            continue
        list_cid = q.subclass_caster_list(access, sid)
        if list_cid is not None:
            return list_cid
    return cid


def _check_spell_list_and_uniqueness(sheet: dict, sources: dict, ident: dict, classes: list,
                                     spells: list, access, v: list[Violation]) -> None:
    granted = _granted_spell_ids(sheet, ident, classes, access)
    seen: set[tuple] = set()

    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        path = f"spells[{i}]"
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
            continue

        if bucket == "class_list":
            continue

        parsed = _parse_source_key(source)
        if parsed is None:
            continue
        kind, oid = parsed
        if kind != "class":
            continue

        list_cid = _effective_list_class(oid, classes, access)
        legal_lists = {list_cid}

        own_level = _level_for_class(classes, oid, access)
        if own_level is not None:
            legal_lists |= set(q.list_widening_classes(access, "class", oid, own_level))
        sub_name = _subclass_for_class(classes, oid, access)
        if sub_name:
            sid = access.resolve("subclass", sub_name)
            if sid:
                legal_lists |= set(q.list_widening_classes(access, "subclass", sid, own_level))
        for c in classes:
            detail_name = c.get("class_detail") if isinstance(c, dict) else None
            if detail_name:
                did = access.resolve("detail_option", detail_name)
                if did:
                    legal_lists |= set(q.list_widening_classes(access, "class_detail", did))
        for feat_entry in sheet.get("features", []) or []:
            fname = feat_entry.get("name") if isinstance(feat_entry, dict) else feat_entry
            oid_opt = access.resolve("class_option", fname)
            if oid_opt:
                legal_lists |= set(q.list_widening_classes(access, "class_option", oid_opt))

        on_a_list = any(q.spell_on_class_list(access, sid_spell, lc) for lc in legal_lists)
        if not on_a_list and sid_spell not in granted:
            v.append(Violation(DOMAIN, "spell-not-on-list", "illegal",
                               f"{name}: not on {source}'s spell list and not otherwise granted", path))


# ── new grimoire-specific checks ─────────────────────────────────────────────


def _check_class_list_legitimacy(sources: dict, spells: list, access,
                                 v: list[Violation]) -> None:
    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        bucket = entry.get("bucket")
        if bucket != "class_list":
            continue

        path = f"spells[{i}]"
        name = entry.get("name")
        source = entry.get("source")
        parsed = _parse_source_key(source)
        if parsed is None:
            v.append(Violation(DOMAIN, "class-list-not-granted", "illegal",
                               f"{name}: invalid source key {source!r}", path))
            continue

        kind, oid = parsed
        choices = q.class_list_spell_choices(access, kind, oid)
        if not choices:
            v.append(Violation(DOMAIN, "class-list-not-granted", "illegal",
                               f"{name}: source {source!r} has no class_list grants", path))
            continue

        sid_spell = access.resolve("spell", name)
        if sid_spell is None:
            continue

        spell_level = entry.get("level")
        if not _int(spell_level):
            spell_level = 0

        valid = False
        for ch in choices:
            lmin = ch.get("spell_level_min")
            lmax = ch.get("spell_level_max")
            if lmin is not None and spell_level < lmin:
                continue
            if lmax is not None and spell_level > lmax:
                continue
            for lc in ch["class_list_ids"]:
                if q.spell_on_class_list(access, sid_spell, lc):
                    valid = True
                    break
            if valid:
                break

        if not valid:
            v.append(Violation(DOMAIN, "class-list-not-granted", "illegal",
                               f"{name}: not a valid class_list choice from {source!r}", path))


def _check_recovery_validity(spells: list, access, v: list[Violation]) -> None:
    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        path = f"spells[{i}]"
        name = entry.get("name")
        spell_level = entry.get("level")
        recovery = entry.get("recovery")

        if spell_level == 0 and recovery not in (None, "at_will", "slotless_per_rest"):
            v.append(Violation(DOMAIN, "invalid-recovery", "illegal",
                               f"{name}: cantrip must have at_will recovery, got {recovery!r}", path))

        if recovery == "ritual_only":
            if not entry.get("ritual_castable"):
                v.append(Violation(DOMAIN, "invalid-recovery", "illegal",
                                   f"{name}: ritual_only recovery but ritual_castable is not true", path))
            sid_spell = access.resolve("spell", name)
            if sid_spell is not None:
                is_ritual = access.db.scalar("SELECT is_ritual FROM spell WHERE id=?", sid_spell)
                if not is_ritual:
                    v.append(Violation(DOMAIN, "invalid-recovery", "illegal",
                                       f"{name}: ritual_only recovery but DB is_ritual=0", path))

        if recovery == "slotless_per_rest":
            uses = entry.get("uses")
            if not isinstance(uses, dict) or not _int(uses.get("max")) or uses["max"] <= 0:
                v.append(Violation(DOMAIN, "invalid-recovery", "illegal",
                                   f"{name}: slotless_per_rest requires uses.max > 0", path))


def _check_ritual_tag(spells: list, access, v: list[Violation]) -> None:
    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        path = f"spells[{i}]"
        name = entry.get("name")
        ritual_castable = entry.get("ritual_castable")
        sid_spell = access.resolve("spell", name)
        if sid_spell is None:
            continue

        is_ritual = access.db.scalar("SELECT is_ritual FROM spell WHERE id=?", sid_spell)
        sheet_ritual = bool(ritual_castable) if ritual_castable is not None else False
        if sheet_ritual != bool(is_ritual):
            v.append(Violation(DOMAIN, "ritual-tag-mismatch", "illegal",
                               f"{name}: ritual_castable={sheet_ritual} but DB is_ritual={is_ritual}",
                               path))


def _check_secondary_cast(spells: list, v: list[Violation]) -> None:
    for i, entry in enumerate(spells):
        if not isinstance(entry, dict):
            continue
        sc = entry.get("secondary_cast")
        if sc is None:
            continue
        if not isinstance(sc, dict):
            v.append(Violation(DOMAIN, "invalid-secondary-cast", "illegal",
                               f"{entry.get('name')}: secondary_cast must be a dict", f"spells[{i}]"))
            continue

        path = f"spells[{i}].secondary_cast"
        resource = sc.get("resource")
        if resource not in VALID_SECONDARY_RESOURCES:
            v.append(Violation(DOMAIN, "invalid-secondary-cast", "illegal",
                               f"{entry.get('name')}: invalid secondary_cast resource {resource!r}", path))
            continue

        if resource == "slotless_per_rest" and (not _int(sc.get("uses")) or sc.get("uses", 0) <= 0):
            v.append(Violation(DOMAIN, "invalid-secondary-cast", "illegal",
                               f"{entry.get('name')}: slotless_per_rest secondary_cast "
                               f"requires uses > 0", path))


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    sources = sheet.get("sources")
    if sources is None or not isinstance(sources, dict):
        return v

    spells = sheet.get("spells", [])
    spells = spells if isinstance(spells, list) else []

    pb = sheet.get("proficiency_bonus")
    ident = _ident(sheet)
    classes = _classes(ident)
    leveled, pact = _classify_casters(classes, access)

    _check_dc_attack(sources, pb, v)
    _check_source_budget_truthfulness(sources, classes, access, v)
    _check_spell_counts(sources, spells, v)
    _check_pact_spells_known(sources, spells, classes, access, v)
    _check_slots(sheet, leveled, pact, access, v)
    _check_spell_list_and_uniqueness(sheet, sources, ident, classes, spells, access, v)
    _check_class_list_legitimacy(sources, spells, access, v)
    _check_recovery_validity(spells, access, v)
    _check_ritual_tag(spells, access, v)
    _check_secondary_cast(spells, v)

    return v
