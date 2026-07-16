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

from access.primitives import fixed_spell_ids, grants_for, resource_at
from access.validator import abilities as abilities_q


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
    where source_key = ``"{kind}:{db_id}"`` (e.g. ``"class:class-a"``).
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
            sub_id = _subclass_id(c, access)
            if not sub_id:
                continue
            level = c.get("level") or 0

            # Category 1: third-caster subclass
            if q.subclass_is_third_caster(access, sub_id):
                ck, prep = q.subclass_cantrips_prepared(access, sub_id, level)
                ability = _class_spellcasting_ability(access, cid, c)
                key = f"class:{cid}"
                sources[key] = {
                    "kind": "class",
                    "ability": ability or "",
                    "cantrips_known": ck or 0,
                    "prepared_limit": prep,
                    "ability_mode": None,
                }
                continue

            # Category 2: grant-only subclass (spells without spellcasting)
            grants = grants_for(access.db, "grant_spell", "subclass", sub_id)
            if not grants:
                continue
            ability = None
            mode = None
            for g in grants:
                if g["ability_id"] and not ability:
                    ability = g["ability_id"]
                am = g["ability_mode"]
                if am and not mode:
                    mode = am
            if not ability:
                continue
            key = f"subclass:{sub_id}"
            sources[key] = {
                "kind": "subclass",
                "ability": ability or "",
                "cantrips_known": sum(1 for g in grants if (g["bucket"] or "") == "cantrip"),
                "prepared_limit": None,
                "ability_mode": mode,
            }
            continue
        level = c.get("level") or 0
        ck, prep = q.cantrips_prepared(access, cid, level)

        ability = _class_spellcasting_ability(access, cid, c)
        # Include source even without ability — pact-magic casters may not
        # have a mapped ability in the test DB but still grant slots/spells.
        key = f"class:{cid}"
        sources[key] = {
            "kind": "class",
            "ability": ability or "",
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
            "ability": ability or "",
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
                    "ability": ability or "",
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
                    "ability": ability or "",
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

def derive_spells(core: dict, prev_grimoire: dict | None, sources: dict, access,
                  chosen_spells: dict | None = None) -> list:
    """Build the ``spells[]`` array: deterministic grants + preserved player choices.

    Deterministic spells come from the ``grant_spell`` spine — subclass always-prepared
    grants, feat-granted spells, species/lineage spells, and pact-caster patron class-list
    expansions.  Player-chosen spells are carried forward from a previous GRIMOIRE
    (append-only — the deriver never deletes).

    ``chosen_spells`` is the generator's spell picks — ``{"cantrips": [spell_id, ...],
    "spells": [spell_id, ...]}`` — resolved from ``choices["spells"]``.  When supplied
    (the generation path) each chosen cantrip/leveled spell is placed on the first CLASS
    source whose spell list carries it and still has budget remaining, so the spellbook
    reflects the model's picks.  When absent (the gold / ``migrate`` path passes nothing)
    this is a no-op and the deterministic behaviour is unchanged.
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
        # Cantrips are always at-will regardless of the grant's stated recovery
        # (single choke-point covering every grant path into the spellbook).
        if entry["level"] == 0:
            entry["recovery"] = "at_will"
        # Full DB metadata
        if spell_row:
            # `school` is an optional STRING in grimoire:1 (no null branch), so omit it when the DB
            # carries none rather than emitting `null`. save_ability/attack_kind/casting_time/range/
            # duration/description each allow null in the contract, so they may stay explicit.
            if spell_row.get("school_id") is not None:
                entry["school"] = spell_row["school_id"]
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
                spell_ids = fixed_spell_ids(access.db, g["id"])
                for sid in spell_ids:
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    uses = _uses_block(g, core, access)
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
                for sid in fixed_spell_ids(access.db, g["id"]):
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    add_spell(srow["name"], source_key, bucket, recovery,
                              spell_row=srow, uses=_uses_block(g, core, access),
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
                for sid in fixed_spell_ids(access.db, g["id"]):
                    srow = _spell_row(access, sid)
                    if not srow:
                        continue
                    add_spell(srow["name"], source_key, bucket, recovery,
                              spell_row=srow, uses=_uses_block(g, core, access),
                              secondary_cast=_secondary_cast(g, sources))

    # ── player-chosen spells (preserved from previous GRIMOIRE) ──
    if prev_grimoire:
        prev_spells = prev_grimoire.get("spells", []) or []
        for ps in prev_spells:
            src = ps.get("source")
            # Only carry forward non-deterministic spells
            if ps.get("bucket") in ("cantrip", "prepared", "known", "class_list"):
                # Check if source still exists
                if src not in sources:
                    continue
                # Preserve as-is (append-only)
                key = (ps["name"], src)
                if key not in seen:
                    seen.add(key)
                    spells.append(dict(ps))

    # ── player-chosen spells (generation path) ──
    # Placed against the per-source DB budgets: a chosen cantrip/leveled spell goes on the first
    # CLASS source whose spell list carries it and still has budget remaining.  Absent chosen picks
    # (the gold / migrate path) this loop does not run, so the deterministic output is unchanged.
    if chosen_spells:
        _place_chosen_spells(chosen_spells, sources, ident, access, add_spell, seen)

    return spells


def _place_chosen_spells(chosen_spells: dict, sources: dict, ident: dict, access,
                         add_spell, seen: set) -> None:
    """Assign the generator's chosen spell ids onto the CLASS sources, honouring the DB budgets.

    Each chosen cantrip is bucketed ``cantrip`` (at-will) and each chosen leveled spell ``prepared``
    (cast from a slot); it lands on the first class source whose effective spell list carries the
    spell and whose remaining count for that bucket is not yet spent.  Spell ids/names resolve from
    the DB — content-neutral.
    """
    from access.validator import spellcasting as q

    classes = ident.get("classes", []) or []

    def _list_class_for(cid: str) -> str:
        """The spell-list class a class source draws from — a third-caster subclass casts from its
        declared list class; otherwise the class casts from its own list."""
        for c in classes:
            if _class_id(c, access) == cid:
                sub = _subclass_id(c, access)
                if sub:
                    lc = q.subclass_caster_list(access, sub)
                    if lc:
                        return lc
                break
        return cid

    list_class: dict[str, str] = {}
    for key, src in sources.items():
        if isinstance(src, dict) and src.get("kind") == "class":
            list_class[key] = _list_class_for(key.split(":", 1)[1])

    def _place(spell_ids, bucket: str, budget_field: str, recovery: str) -> None:
        # Remaining budget per class source (None = untabulated → unlimited, matching the validator,
        # which flags only counts that EXCEED an integer budget).
        remaining: dict[str, int | None] = {}
        for key, src in sources.items():
            if isinstance(src, dict) and src.get("kind") == "class":
                b = src.get(budget_field)
                remaining[key] = b if _is_int(b) else None
        for sid in spell_ids or []:
            srow = _spell_row(access, sid)
            if not srow:
                continue
            for key in list_class:
                if (srow["name"], key) in seen:
                    break  # already on this source (e.g. an always-grant) — nothing to place
                if not q.spell_on_class_list(access, sid, list_class[key]):
                    continue
                if remaining[key] is not None and remaining[key] <= 0:
                    continue
                add_spell(srow["name"], key, bucket, recovery, spell_row=srow)
                if remaining[key] is not None:
                    remaining[key] -= 1
                break

    _place(chosen_spells.get("cantrips"), "cantrip", "cantrips_known", "at_will")
    _place(chosen_spells.get("spells"), "prepared", "prepared_limit", "spell_slot")


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
        # Minimal fallback for a reduced test DB. Read school_id when the column exists so a spell's
        # school still reaches the grimoire; everything else degrades to defaults.
        row = access.db.one("SELECT id, name, level, is_ritual, 0 as concentration FROM spell WHERE id = ?", spell_id)
        if not row:
            return None
        result = {
            "id": row[0], "name": row[1], "level": row[2],
            "is_ritual": row[3], "concentration": row[4],
        }
        try:
            school = access.db.scalar("SELECT school_id FROM spell WHERE id = ?", spell_id)
            if school is not None:
                result["school_id"] = school
        except Exception:
            pass
        return result
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


def _grant_field(grant_row, field):
    """Read a named column from a grant row, tolerating minimal test rows."""
    try:
        return grant_row[field]
    except (KeyError, IndexError):
        return None


def _uses_block(grant_row, core, access) -> dict | None:
    """Extract a uses block from a grant_spell row.

    A static ``uses_num`` is used verbatim.  When ``uses_num`` is NULL the
    maximum is derived from ``uses_kind`` and grounded in the build:
    ``proficiency_bonus`` → the sheet's proficiency bonus; ``ability_modifier``
    → the modifier of the named ability's final score; ``class_resource`` → the
    named resource's maximum at the owning class's level.
    """
    un = _grant_field(grant_row, "uses_num")
    max_val = un
    if max_val is None:
        max_val = _dynamic_uses_max(grant_row, core, access)
    if max_val is None:
        return None
    uses = {"max": max_val}
    rid = _grant_field(grant_row, "recharge_id")
    if rid:
        uses["recharge"] = rid
    return uses


def _dynamic_uses_max(grant_row, core, access) -> int | None:
    """Compute a dynamic per-rest use maximum from the grant's ``uses_kind``.

    Returns ``None`` when the kind is absent/static or cannot be grounded.
    Per-rest use counts have a floor of one use ("a minimum of once")."""
    kind = _grant_field(grant_row, "uses_kind")
    if not kind:
        return None

    if kind == "proficiency_bonus":
        pb = core.get("proficiency_bonus")
        return max(1, pb) if _is_int(pb) else None

    if kind == "ability_modifier":
        aid = _grant_field(grant_row, "uses_ability_id")
        mod = _core_ability_mod(aid, core, access)
        # A per-rest ability_modifier grant always yields at least one use: apply
        # the floor even when the ability can't be grounded, so a valid dynamic
        # grant never produces uses.max < 1 (slotless_per_rest requires > 0).
        if mod is None:
            return 1
        return max(1, mod)

    if kind == "class_resource":
        rid = _grant_field(grant_row, "uses_resource_id")
        if not rid:
            return None
        return _class_resource_max(rid, core, access)

    return None


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _core_ability_mod(aid, core, access) -> int | None:
    """Modifier of the CORE ability named by a DB ability id, or None if it can't
    be grounded. A grant references the full DB ability id (e.g. the long-form id),
    whereas CORE keys abilities by their short code; map the id to that short code
    via the ability table's abbrev before reading the final score."""
    if not aid:
        return None
    abilities = core.get("abilities", {}) or {}
    ab = abilities.get(aid)
    if not isinstance(ab, dict):
        # CORE keys abilities by the short code; normalise those keys to the full DB id
        # (the shared helper backs the abbrev lookup) and index by the grant's id.
        norm = {abilities_q.ability_id_for_short_key(access, k): val for k, val in abilities.items()}
        ab = norm.get(aid)
    if not isinstance(ab, dict):
        return None
    final = ab.get("final")
    if not _is_int(final):
        return None
    return (final - 10) // 2


def _class_resource_max(resource_id: str, core, access) -> int | None:
    """Maximum count of a class resource at the owning class's level, grounded in
    the resource ladder (``class_resource_level``), falling back to the CORE
    resource budgets by name."""
    owner = access.db.one(
        "SELECT owner_kind, owner_id, name FROM class_resource WHERE id=?", resource_id)
    level = 0
    res_name = None
    if owner is not None:
        res_name = owner["name"] if hasattr(owner, "keys") else owner[2]
        okind = owner["owner_kind"] if hasattr(owner, "keys") else owner[0]
        oid = owner["owner_id"] if hasattr(owner, "keys") else owner[1]
        if okind == "class" and oid:
            level = _class_level_for(oid, core, access)
    row = resource_at(access.db, resource_id, level)
    if row is not None:
        count = row["count"] if hasattr(row, "keys") else None
        if count is not None:
            return count
    # Fallback: the CORE resource budget keyed by the resource's display name.
    if res_name:
        budget = (core.get("resource_budgets", {}) or {}).get(res_name)
        if isinstance(budget, dict) and _is_int(budget.get("max")):
            return budget["max"]
    return None


def _class_level_for(class_id: str, core, access) -> int:
    """The character's level in a given class id (0 if not taken)."""
    for c in (core.get("identity", {}) or {}).get("classes", []) or []:
        if _class_id(c, access) == class_id:
            return c.get("level") or 0
    return 0


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


DURATION_KIND_MAP = {
    "time-span": None,  # uses duration_unit_id instead
    "concentration": None,  # uses duration_unit_id instead (concentration flag already set)
    "until-dispelled-or-triggered": "until_dispelled",
}
DURATION_UNIT_KIND = {"round": "round", "minute": "minute", "hour": "hour", "day": "day"}


def _format_duration(row) -> dict | None:
    dt = row.get("duration_type_id")
    if not dt:
        return None
    kind = DURATION_KIND_MAP.get(dt, dt)
    if kind is None:  # time-span — resolve from duration_unit_id
        kind = DURATION_UNIT_KIND.get(row.get("duration_unit_id"), "special")
    result = {"kind": kind}
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
    has_other_casters = False

    for c in ident.get("classes", []) or []:
        cid = _class_id(c, access)
        if not cid:
            continue
        level = c.get("level") or 0
        prog = q.caster_progression(access, cid) or "none"

        if prog == "full":
            leveled_level += level
            has_other_casters = True
        elif prog == "half":
            leveled_level += (level + 1) // 2  # ceil(level/2)
            has_other_casters = True
        elif prog == "pact":
            pact_levels.append((cid, level))
        # Check for third-caster subclass
        sub_id = _subclass_id(c, access)
        if sub_id and prog in ("none",):
            if q.subclass_is_third_caster(access, sub_id):
                leveled_level += level // 3

    # Leveled slots
    spell_slots = {}
    if leveled_level > 0:
        if not has_other_casters:
            # Solo third-caster: use subclass slot table directly
            for c in ident.get("classes", []) or []:
                cid = _class_id(c, access)
                if not cid:
                    continue
                level = c.get("level") or 0
                sub_id = _subclass_id(c, access)
                if sub_id and q.subclass_is_third_caster(access, sub_id):
                    slots = q.subclass_slots(access, sub_id, level)
                    for sl, count in slots.items():
                        spell_slots[str(sl)] = {"max": count}
        else:
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

def derive_grimoire(core: dict, prev_grimoire: dict | None, access,
                    chosen_spells: dict | None = None) -> dict:
    """Produce a ``grimoire:1`` dict from CORE + optional previous GRIMOIRE + DB.

    ``chosen_spells`` (``{"cantrips": [...], "spells": [...]}`` from ``choices["spells"]``) folds the
    generator's spell picks into the spellbook when supplied.  Omitted (the gold / ``migrate`` path),
    the deriver behaves exactly as before — re-derived purely from the class progression + grants.
    """
    sources = derive_sources(core, access)
    spells = derive_spells(core, prev_grimoire, sources, access, chosen_spells=chosen_spells)
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
