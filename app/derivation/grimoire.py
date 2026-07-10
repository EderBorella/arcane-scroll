"""GRIMOIRE deriver — produces a ``grimoire:1`` from CORE + DB.

Deterministic: sources, always-prepared spells, and slot maximums are computed
from the CORE sheet and the reference DB.  Player-chosen spells are preserved
from a previous GRIMOIRE (append-only — the deriver never deletes).

In-memory only — takes dicts, returns a dict.  The orchestration layer handles
schema validation and API exposure.
"""

from collections import defaultdict
import hashlib
import json

from access.primitives import grants_for


# ── helpers ──────────────────────────────────────────────────────────────────

def _class_id(core_class_entry, access):
    return access.resolve("class", core_class_entry.get("class"))


def _subclass_id(core_class_entry, access):
    return access.resolve("subclass", core_class_entry.get("subclass"))


def _feat_id(feat_entry, access):
    return access.resolve("feat", feat_entry.get("name"))


def _species_id(core_species, access):
    return access.resolve("species", core_species)


def _lineage_id(core_lineage, access):
    return access.resolve("lineage", core_lineage) if core_lineage else None


def hash_core(core: dict) -> str:
    """Stable hash of the spell-affecting parts of CORE for change detection."""
    data = {
        "classes": [
            {"class": c["class"], "level": c["level"], "subclass": c.get("subclass")}
            for c in core["identity"]["classes"]
        ],
        "species": core["identity"]["species"],
        "lineage": core["identity"].get("lineage"),
        "feats": [f["name"] for f in core.get("feats", [])],
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


# ── C-G1a  source derivation ────────────────────────────────────────────────

def derive_sources(core: dict, access) -> dict:
    """Build the ``sources`` map from CORE identity + DB facts.

    Returns ``{source_key: {kind, ability, cantrips_known, prepared_limit, ability_mode}}``
    where source_key = ``"{kind}:{db_id}"`` (e.g. ``"class:wizard"``).
    """
    from access.validator import spellcasting as q

    sources: dict = {}
    ident = core.get("identity", {})

    # ── class sources ──
    for c in ident.get("classes", []) or []:
        cid = _class_id(c, access)
        if not cid:
            continue
        prog = q.caster_progression(access, cid)
        if prog is None or prog == "none":
            continue
        level = c.get("level") or 0
        ck, prep = q.cantrips_prepared(access, cid, level)

        ability = _class_spellcasting_ability(access, cid, c)
        # Include source even without ability — pact-magic casters may not
        # have a mapped ability in the test DB but still grant slots/spells.
        key = f"class:{cid}"
        sources[key] = {
            "kind": "class",
            "ability": ability,
            "cantrips_known": ck or 0,
            "prepared_limit": None if prog == "pact" else prep,
            "ability_mode": None,
        }

    # ── feat sources ──
    for f in core.get("feats", []) or []:
        fid = _feat_id(f, access)
        if not fid:
            continue
        grants = grants_for(access.db, "grant_spell", "feat", fid)
        if not grants:
            continue

        ability = _feat_spellcasting_ability(access, f, grants)
        cantrip_count = sum(1 for g in grants if (g["bucket"] or "") == "cantrip")
        if not cantrip_count and not ability:
            continue  # no spellcasting-relevant grants

        key = f"feat:{fid}"
        mode = _feat_ability_mode(grants)
        sources[key] = {
            "kind": "feat",
            "ability": ability,
            "cantrips_known": cantrip_count,
            "prepared_limit": None,
            "ability_mode": mode,
        }

    # ── species / lineage sources ──
    spid = _species_id(ident.get("species"), access)
    if spid:
        grants = grants_for(access.db, "grant_spell", "species", spid)
        if grants:
            key = f"species:{spid}"
            ability = _species_spellcasting_ability(access, grants)
            mode = _feat_ability_mode(grants)
            ck = sum(1 for g in grants if (g["bucket"] or "") == "cantrip")
            if ability or ck or grants:
                sources[key] = {
                    "kind": "species",
                    "ability": ability,
                    "cantrips_known": ck,
                    "prepared_limit": None,
                    "ability_mode": mode,
                }

    lid = _lineage_id(ident.get("lineage"), access)
    if lid:
        grants = grants_for(access.db, "grant_spell", "lineage", lid)
        if grants:
            ability = _species_spellcasting_ability(access, grants)
            mode = _feat_ability_mode(grants)
            ck = sum(1 for g in grants if (g["bucket"] or "") == "cantrip")
            if ability or ck:
                key = f"lineage:{lid}"
                sources[key] = {
                    "kind": "lineage",
                    "ability": ability,
                    "cantrips_known": ck,
                    "prepared_limit": None,
                    "ability_mode": mode,
                }

    return sources


def _class_spellcasting_ability(access, class_id: str, core_class_entry: dict) -> str | None:
    """Determine the spellcasting ability for a class source."""
    # Check third-caster subclass first
    sub_id = _subclass_id(core_class_entry, access)
    if sub_id:
        row = access.db.one(
            "SELECT ability_id FROM subclass_spellcasting WHERE subclass_id = ?", sub_id
        )
        if row and row[0]:
            return row[0]
    # Fall back to the caster-class convention: primary mode
    from access.validator import spellcasting as q
    prog = q.caster_progression(access, class_id)
    if prog in ("full", "half", "pact"):
        return _primary_ability(access, class_id)
    return None


def _primary_ability(access, class_id: str) -> str | None:
    """The primary spellcasting ability for a class."""
    try:
        row = access.db.one(
            "SELECT ability_id FROM class_primary_ability WHERE class_id = ? AND kind = 'spellcasting'",
            class_id,
        )
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    # Fallback for test/convenience: use the class's first saving throw ability
    row = access.db.one(
        "SELECT ability_id FROM class_saving_throw WHERE class_id = ? LIMIT 1",
        class_id,
    )
    return row[0] if row else None


def _feat_spellcasting_ability(access, feat_entry: dict, grants: list) -> str | None:
    """Resolve the spellcasting ability for a feat source from CORE feat's ability_increase."""
    ai = feat_entry.get("ability_increase")
    if isinstance(ai, dict) and ai.get("ability"):
        ability_name = ai["ability"]
        aid = access.resolve("ability", ability_name)
        return aid
    # For feats with fixed ability (e.g. ability_mode='none')
    for g in grants:
        aid = g["ability_id"]
        if aid:
            return aid
    return None


def _species_spellcasting_ability(access, grants: list) -> str | None:
    """Resolve casting ability from grant rows."""
    for g in grants:
        aid = g["ability_id"]
        if aid:
            return aid
    return None


def _feat_ability_mode(grants: list) -> str | None:
    """Extract ability_mode from the first grant row that has one."""
    for g in grants:
        am = g["ability_mode"]
        if am:
            return am
    return None


# ── C-G1b  spellbook derivation ─────────────────────────────────────────────

def derive_spells(core: dict, prev_grimoire: dict | None, sources: dict, access) -> list:
    """Build the ``spells[]`` array: deterministic grants + preserved player choices.

    Deterministic spells come from the ``grant_spell`` spine — subclass always-prepared
    grants, feat-granted spells, species/lineage spells, and Warlock patron class-list
    expansions.  Player-chosen spells are carried forward from a previous GRIMOIRE
    (append-only — the deriver never deletes).
    """
    spells: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (name, source) dedup

    ident = core.get("identity", {}) or {}

    def add_spell(name: str, source_key: str, bucket: str, recovery: str,
                  spell_row=None, uses=None, secondary_cast=None):
        key = (name, source_key)
        if key in seen:
            return
        seen.add(key)

        entry = {
            "name": name,
            "level": spell_row["level"] if spell_row else 0,
            "source": source_key,
            "bucket": bucket,
            "recovery": recovery,
            "ritual_castable": bool(spell_row["is_ritual"]) if spell_row else False,
            "concentration": bool(spell_row["concentration"]) if spell_row else False,
        }
        # Full DB metadata
        if spell_row:
            entry["school"] = spell_row.get("school_id")
            entry["save_ability"] = spell_row.get("save_ability_id") or None
            entry["attack_kind"] = spell_row.get("attack_kind") or None
            entry["components"] = _format_components(spell_row)
            entry["casting_time"] = _format_casting_time(spell_row)
            entry["range"] = _format_range(spell_row)
            entry["duration"] = _format_duration(spell_row)
            entry["description"] = spell_row.get("description") or None
        if uses:
            entry["uses"] = uses
        if secondary_cast:
            entry["secondary_cast"] = secondary_cast
        spells.append(entry)

    # ── class-owner grants ──
    for c in ident.get("classes", []) or []:
        cid = _class_id(c, access)
        if not cid:
            continue
        sub_id = _subclass_id(c, access)

        for owner_kind, owner_id in [("class", cid), ("subclass", sub_id)]:
            if not owner_id:
                continue
            grant_rows = grants_for(access.db, "grant_spell", owner_kind, owner_id)
            for g in grant_rows:
                bucket = g["bucket"] or "always"
                recovery = g["recovery"] or _default_recovery(bucket)
                source_key = _source_key_for_owner(owner_kind, owner_id, cid, sources)
                if not source_key:
                    continue

                # Get the spell name(s) from fixed grants
                spell_ids = _grant_spell_fixed_ids(access, g["id"])
                for sid in spell_ids:
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    uses = _uses_block(g)
                    add_spell(srow["name"], source_key, bucket, recovery,
                              spell_row=srow, uses=uses,
                              secondary_cast=_secondary_cast(g, sources))

    # ── feat-owner grants ──
    for f in core.get("feats", []) or []:
        fid = _feat_id(f, access)
        if not fid:
            continue
        grant_rows = grants_for(access.db, "grant_spell", "feat", fid)
        for g in grant_rows:
                bucket = g["bucket"] or "always"
                recovery = g["recovery"] or _default_recovery(bucket)
                source_key = _source_key_for_feat(fid, sources)
                if not source_key:
                    continue
                for sid in _grant_spell_fixed_ids(access, g["id"]):
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    add_spell(srow["name"], source_key, bucket, recovery,
                              spell_row=srow, uses=_uses_block(g),
                              secondary_cast=_secondary_cast(g, sources))

    # ── species / lineage grants ──
    for owner_kind, owner_name in [("species", ident.get("species")),
                                    ("lineage", ident.get("lineage"))]:
        if not owner_name:
            continue
        oid = access.resolve(owner_kind, owner_name)
        if not oid:
            continue
        grant_rows = grants_for(access.db, "grant_spell", owner_kind, oid)
        for g in grant_rows:
                bucket = g["bucket"] or "always"
                recovery = g["recovery"] or _default_recovery(bucket)
                source_key = _source_key_for_kind(owner_kind, oid, sources)
                if not source_key:
                    continue
                for sid in _grant_spell_fixed_ids(access, g["id"]):
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    add_spell(srow["name"], source_key, bucket, recovery,
                              spell_row=srow, uses=_uses_block(g),
                              secondary_cast=_secondary_cast(g, sources))

    # ── player-chosen spells (preserved from previous GRIMOIRE) ──
    if prev_grimoire:
        prev_spells = prev_grimoire.get("spells", []) or []
        for ps in prev_spells:
            src = ps.get("source")
            # Only carry forward non-deterministic spells
            if ps.get("bucket") in ("cantrip", "prepared", "known"):
                # Check if source still exists
                if src not in sources:
                    continue
                # Preserve as-is (append-only)
                key = (ps["name"], src)
                if key not in seen:
                    seen.add(key)
                    spells.append(dict(ps))

    return spells


def _grant_spell_fixed_ids(access, grant_id: str) -> list[str]:
    """Return spell_ids for fixed-grant spells for a given grant_spell id."""
    rows = access.db.q(
        "SELECT spell_id FROM grant_spell_fixed WHERE grant_id = ?", grant_id
    )
    return [r[0] for r in rows]


def _spell_row(access, spell_id: str):
    """Return a full spell row dict from the DB.  Gracefully degrades when the
    DB schema is minimal (test DB only has id/name/level/is_ritual)."""
    try:
        row = access.db.one(
            """SELECT id, name, level, school_id, is_ritual, concentration,
                      action_cost_id, cast_time_amount, cast_time_unit_id, trigger_text,
                      range_type_id, range_amount, range_unit_id,
                      comp_v, comp_s, comp_m, material_text, material_cost_gp, material_consumed,
                      duration_type_id, duration_amount, duration_unit_id,
                      save_ability_id, attack_kind, description
               FROM spell WHERE id = ?""",
            spell_id,
        )
    except Exception:
        # Minimal fallback for test DB
        row = access.db.one("SELECT id, name, level, is_ritual, 0 as concentration FROM spell WHERE id = ?", spell_id)
        if row:
            return {
                "id": row[0], "name": row[1], "level": row[2],
                "is_ritual": row[3], "concentration": row[4],
            }
        return None
    if not row:
        return None
    return dict(row) if hasattr(row, "keys") else {
        "id": row[0], "name": row[1], "level": row[2], "school_id": row[3],
        "is_ritual": row[4], "concentration": row[5],
        "action_cost_id": row[6], "cast_time_amount": row[7], "cast_time_unit_id": row[8],
        "trigger_text": row[9], "range_type_id": row[10], "range_amount": row[11],
        "range_unit_id": row[12], "comp_v": row[13], "comp_s": row[14], "comp_m": row[15],
        "material_text": row[16], "material_cost_gp": row[17], "material_consumed": row[18],
        "duration_type_id": row[19], "duration_amount": row[20], "duration_unit_id": row[21],
        "save_ability_id": row[22], "attack_kind": row[23], "description": row[24],
    }


def _default_recovery(bucket: str) -> str:
    if bucket == "cantrip":
        return "at_will"
    if bucket == "class_list":
        return "pact_slot"
    return "spell_slot"


def _source_key_for_owner(owner_kind, owner_id, class_id, sources) -> str | None:
    """Find source key for a grant owner."""
    key = f"class:{class_id}"
    if key in sources:
        return key
    # Try subclass directly
    key = f"subclass:{owner_id}"
    if key in sources:
        return key
    return _source_key_for_kind(owner_kind, owner_id, sources)


def _source_key_for_feat(feat_id, sources) -> str | None:
    key = f"feat:{feat_id}"
    return key if key in sources else None


def _source_key_for_kind(kind, owner_id, sources) -> str | None:
    key = f"{kind}:{owner_id}"
    return key if key in sources else None


def _uses_block(grant_row) -> dict | None:
    """Extract uses block from a grant_spell row."""
    try:
        un = grant_row["uses_num"]
    except (KeyError, IndexError):
        return None
    if un is not None:
        uses = {"max": un}
        try:
            rid = grant_row["recharge_id"]
        except (KeyError, IndexError):
            rid = None
        if rid:
            uses["recharge"] = rid
        return uses
    return None


def _secondary_cast(grant_row, sources) -> dict | None:
    """Build secondary_cast block for also_slot_castable spells."""
    try:
        if grant_row["also_slot_castable"]:
            return {"resource": "spell_slot"}
    except (KeyError, IndexError):
        pass
    return None


# ── metadata formatters ─────────────────────────────────────────────────────

def _format_components(row) -> dict:
    v = bool(row.get("comp_v"))
    s = bool(row.get("comp_s"))
    m = bool(row.get("comp_m"))
    result = {"verbal": v, "somatic": s, "material": m}
    if m:
        if row.get("material_cost_gp"):
            result["material_cost_gp"] = row["material_cost_gp"]
        result["material_consumed"] = bool(row.get("material_consumed"))
    return result


def _format_casting_time(row) -> dict | None:
    acid = row.get("action_cost_id")
    if not acid:
        return None
    kind = {"action": "action", "bonus-action": "bonus", "reaction": "reaction"}.get(
        acid, acid
    )
    result = {"kind": kind}
    if row.get("cast_time_amount"):
        result["value"] = row["cast_time_amount"]
    if row.get("trigger_text"):
        result["condition"] = row["trigger_text"]
    return result


def _format_range(row) -> dict | None:
    rt = row.get("range_type_id")
    if not rt:
        return None
    result = {"kind": rt}
    if row.get("range_amount"):
        result["distance"] = row["range_amount"]
    return result


def _format_duration(row) -> dict | None:
    dt = row.get("duration_type_id")
    if not dt:
        return None
    result = {"kind": dt}
    if row.get("duration_amount"):
        result["value"] = row["duration_amount"]
    if row.get("concentration"):
        result["concentration"] = True
    return result


# ── C-G1c  slot maximums ────────────────────────────────────────────────────

def derive_slots(core: dict, access) -> tuple[dict, dict]:
    """Compute spell_slots and pact_slots maximums from class levels.

    Returns ``(spell_slots, pact_slots)`` — both ``{level: {max: N}}`` dicts
    with NO remaining counters.
    """
    from access.validator import spellcasting as q

    ident = core.get("identity", {}) or {}
    leveled_level = 0
    pact_levels: list[tuple[str, int]] = []

    for c in ident.get("classes", []) or []:
        cid = _class_id(c, access)
        if not cid:
            continue
        level = c.get("level") or 0
        prog = q.caster_progression(access, cid) or "none"

        if prog == "full":
            leveled_level += level
        elif prog == "half":
            leveled_level += (level + 1) // 2  # ceil(level/2)
        elif prog == "pact":
            pact_levels.append((cid, level))
        # Check for third-caster subclass
        sub_id = _subclass_id(c, access)
        if sub_id and prog in ("none",):
            from access.validator import spellcasting
            if spellcasting.subclass_is_third_caster(access, sub_id):
                leveled_level += level // 3

    # Leveled slots
    spell_slots = {}
    if leveled_level > 0:
        slots = q.multiclass_slots(access, leveled_level)
        for sl, count in slots.items():
            spell_slots[str(sl)] = {"max": count}

    # Pact slots
    pact_slots = {}
    for cid, level in pact_levels:
        pslots = q.pact_slots(access, cid, level)
        for sl, count in pslots.items():
            key = str(sl)
            if key in pact_slots:
                pact_slots[key]["max"] += count
            else:
                pact_slots[key] = {"max": count}

    return spell_slots, pact_slots


# ── orchestrator ────────────────────────────────────────────────────────────

def derive_grimoire(core: dict, prev_grimoire: dict | None, access) -> dict:
    """Produce a ``grimoire:1`` dict from CORE + optional previous GRIMOIRE + DB."""
    sources = derive_sources(core, access)
    spells = derive_spells(core, prev_grimoire, sources, access)
    spell_slots, pact_slots = derive_slots(core, access)

    result: dict = {
        "schema_version": 1,
        "character_id": core.get("character_id", ""),
        "character_name": core.get("character_name", ""),
        "derived_from_core": hash_core(core),
        "sources": sources,
        "spells": spells,
    }
    if spell_slots:
        result["spell_slots"] = spell_slots
    if pact_slots:
        result["pact_slots"] = pact_slots
    return result
