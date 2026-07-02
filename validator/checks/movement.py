"""Layer: movement. When speed_detail is present, verify: its base equals the species' base walking
speed and base_source names the species; base_mode is a real speed key; the speeds map re-derives from
the detail (self-consistency, incl. relative modes); and every modifier's source is something the
character actually carries (species / feature / feat / item). Provenance is optional, so with no
speed_detail the layer stays silent. Grounded in the species data and the sheet itself."""
from validator.report import Violation, WARNING

LAYER = "movement"


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def _derive(detail):
    """Re-derive final speed per mode from speed_detail: for a mode, (base if it is base_mode else 0)
    plus each modifier's value, or factor × final(of) for a relative modifier. Relative refs are
    resolved iteratively (they may chain); unresolved refs are left out."""
    base, base_mode = detail.get("base") or 0, detail.get("base_mode")
    mods = detail.get("modifiers") or []

    def fixed(mode):
        tot = base if mode == base_mode else 0
        for m in mods:
            if m.get("mode") == mode and "value" in m:
                tot += m.get("value") or 0
        return tot

    modes = {m.get("mode") for m in mods} | ({base_mode} if base_mode else set())
    modes.discard(None)
    final = {mode: fixed(mode) for mode in modes}
    for _ in range(len(mods) + 1):
        changed = False
        for m in mods:
            rel = m.get("relative")
            if rel and rel.get("of") in final:
                val = fixed(m.get("mode")) + round((rel.get("factor", 1) or 1) * final[rel["of"]])
                if final.get(m.get("mode")) != val:
                    final[m.get("mode")], changed = val, True
        if not changed:
            break
    return final


def _character_sources(sheet):
    """Normalised identifiers the character carries that could grant/adjust a speed."""
    ident = sheet.get("identity") or {}
    s = {_norm(ident.get("species"))}
    for f in (sheet.get("feats") or []):
        s.add(_norm(f.get("name")))
    for f in (sheet.get("features") or []):
        s.add(_norm(f.get("name")))
    for it in (sheet.get("backpack") or []):
        s.add(_norm(it.get("name")))
    for it in ((sheet.get("equipped") or {}).values()):
        s.add(_norm(it.get("name")))
    s.discard("")
    return s


def check(sheet, rules):
    out = []
    combat = sheet.get("combat") or {}
    detail = combat.get("speed_detail")
    if not detail:
        return out
    speeds = combat.get("speed") or {}
    species = (sheet.get("identity") or {}).get("species")

    exp = rules.species_base_speed(species)
    if exp is not None and detail.get("base") is not None and detail["base"] != exp:
        out.append(Violation(LAYER, "base_speed_mismatch",
                             f"base walking speed {detail['base']} != species '{species}' speed {exp}",
                             exp, detail["base"]))

    bs = detail.get("base_source")
    if bs is not None and species is not None and _norm(bs) != _norm(species):
        out.append(Violation(LAYER, "base_source_not_species",
                             f"base_source '{bs}' is not the character's species '{species}'",
                             species, bs, severity=WARNING))

    bm = detail.get("base_mode")
    if bm is not None and bm not in speeds:
        out.append(Violation(LAYER, "base_mode_absent",
                             f"base_mode '{bm}' is not a key in the speeds map", list(speeds), bm))

    for mode, val in _derive(detail).items():
        if mode in speeds and speeds[mode] != val:
            out.append(Violation(LAYER, "speed_not_derivable",
                                 f"speed['{mode}'] = {speeds[mode]} but speed_detail derives {val}",
                                 val, speeds[mode]))

    known = _character_sources(sheet)
    for m in (detail.get("modifiers") or []):
        src = m.get("source")
        if src and _norm(src) not in known:
            out.append(Violation(LAYER, "speed_source_unknown",
                                 f"speed modifier source '{src}' is not among the character's "
                                 f"species / features / feats / items", None, src, severity=WARNING))
    return out
