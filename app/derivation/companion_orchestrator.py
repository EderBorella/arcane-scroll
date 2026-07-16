"""COMPANION orchestrator. Drives the concrete-companion deriver to produce a
companion-modifier:1 dict. Three modes mirror the MODIFIER orchestrator:

  * ``fill`` with no existing sheet — fill from scratch;
  * ``fill`` with an existing sheet — fill gaps + preserve non-overwritable
    session fields via a deep merge keyed by ``companion_index``;
  * ``validate`` — skip derivation, echo the existing sheet.

Non-overwritable fields are a companion's live session state (current/temp HP,
remaining hit dice, active states); a re-derive must never clobber them.
"""
from app.derivation.companion import derive_companion_modifiers


# ── non-overwritable field paths (session state on a companion) ──────────────
# Paths are matched from the top of the companion sheet. companion_modifiers is
# an array merged by companion_index, so each element's live path is
# "companion_modifiers.<index>.<field...>".

NON_OVERWRITABLE = frozenset({
    "companion_modifiers.*.hit_points.current",
    "companion_modifiers.*.hit_points.temp",
    "companion_modifiers.*.hit_dice.*.remaining",
    "companion_modifiers.*.character_states",
})


def _match_path(path: str, pattern: str) -> bool:
    parts = path.split(".")
    pat_parts = pattern.split(".")
    if len(parts) != len(pat_parts):
        return False
    for p, pp in zip(parts, pat_parts):
        if pp != "*" and p != pp:
            return False
    return True


def _is_non_overwritable(path: str) -> bool:
    return any(_match_path(path, pat) for pat in NON_OVERWRITABLE)


def _deep_merge(base: dict, existing: dict, path: str = "") -> dict:
    """Merge existing into base, preserving non-overwritable fields as-is. The
    companion_modifiers array is merged by companion_index; other arrays are
    replaced by the derived (base) value."""
    result = {}
    for key in list(base) + [k for k in existing if k not in base]:
        child_path = f"{path}.{key}" if path else key
        base_val = base.get(key)
        exist_val = existing.get(key)

        if _is_non_overwritable(child_path):
            if key in existing:
                result[key] = exist_val
            elif key in base:
                result[key] = base_val
        elif key == "companion_modifiers" and isinstance(base_val, list) \
                and isinstance(exist_val, list):
            result[key] = _merge_companions(base_val, exist_val, child_path)
        elif isinstance(base_val, dict) and isinstance(exist_val, dict):
            result[key] = _deep_merge(base_val, exist_val, child_path)
        elif key in base:
            result[key] = base_val
        else:
            result[key] = exist_val
    return result


def _merge_companions(base: list, existing: list, path: str) -> list:
    """Merge two companion_modifiers arrays by companion_index. For a matched pair,
    non-overwritable session sub-fields are preserved from the existing entry."""
    existing_by_index = {}
    for item in existing:
        if isinstance(item, dict) and isinstance(item.get("companion_index"), int):
            existing_by_index[item["companion_index"]] = item

    result = []
    seen = set()
    for base_item in base:
        if not isinstance(base_item, dict):
            result.append(base_item)
            continue
        idx = base_item.get("companion_index")
        seen.add(idx)
        exist_item = existing_by_index.get(idx)
        if not isinstance(exist_item, dict):
            result.append(base_item)
            continue
        result.append(_merge_companion_entry(base_item, exist_item, f"{path}.{idx}"))

    # Retain any existing entry the deriver did not produce (its creature could not
    # be resolved this run) so hand-tracked session state is never dropped.
    for item in existing:
        if isinstance(item, dict) and item.get("companion_index") not in seen:
            result.append(item)
    return result


def _merge_companion_entry(base_item: dict, exist_item: dict, path: str) -> dict:
    merged = {}
    for k, bv in base_item.items():
        child_path = f"{path}.{k}"
        if _is_non_overwritable(child_path) and k in exist_item:
            merged[k] = exist_item[k]
        elif isinstance(bv, dict) and isinstance(exist_item.get(k), dict):
            merged[k] = _deep_merge(bv, exist_item[k], child_path)
        else:
            merged[k] = bv
    for k, ev in exist_item.items():
        if k not in merged and _is_non_overwritable(f"{path}.{k}"):
            merged[k] = ev
    return merged


# ── orchestrator ─────────────────────────────────────────────────────────────


def derive_companions(core: dict, existing_companion: dict | None, mode: str,
                      access) -> tuple[dict, dict]:
    """Produce a companion-modifier:1 dict. Returns (sheet, meta)."""
    meta = {"mode": mode, "derived": mode != "validate"}

    if mode == "validate":
        if existing_companion is None:
            return {}, meta
        return dict(existing_companion), meta

    modifiers = derive_companion_modifiers(core, access)

    full = {
        "schema_version": 1,
        "character_id": (core or {}).get("character_id", ""),
        "character_name": (core or {}).get("character_name", ""),
        "companion_modifiers": modifiers,
    }

    if mode == "fill" and existing_companion is not None:
        full = _deep_merge(full, existing_companion)

    return full, meta
