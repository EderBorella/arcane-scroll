"""Spellcasting — save DC + attack bonus per casting class, spell slots by level, and the chosen
spells bucketed by level (tagged prepared vs known)."""
from app.derivation.abilities import modifier
from app.generation import helpers as H


def spell_stats(cat, scores, prof_bonus, classes) -> dict:
    """{class name: {ability, save_dc, attack_bonus}} for each class that can cast at its level."""
    out = {}
    for ci, lv in classes:
        c = cat.record("classes", ci)
        sc = (c or {}).get("spellcasting")
        if not sc or not (H.has_slots(cat, ci, lv) or H.cantrips_known(cat, ci, lv)):
            continue
        ab = sc["spellcasting_ability"]["index"]
        mod = modifier(scores[ab])
        out[c["name"]] = {"ability": ab, "save_dc": 8 + prof_bonus + mod, "attack_bonus": prof_bonus + mod}
    return out


_DENOM = {"full": 1, "half": 2, "third": 3}      # caster-level contribution = level // denom


def _unpack(item):
    """A class entry as (index, level, subclass) — accepts (ci, lv) or (ci, lv, sub)."""
    return item[0], item[1], (item[2] if len(item) > 2 else None)


def _caster_share(prog, thirds, ci, lv, sub) -> int:
    """One class's contribution to the combined caster level. full=level, half=level//2,
    third-caster *subclass* (EK/AT)=level//3, pact (Warlock) / non-caster = 0."""
    p = prog.get(ci)
    if p in _DENOM:
        return lv // _DENOM[p]
    if sub and H._norm(sub) in thirds:                       # third-caster subclass on a non-caster base
        return lv // 3
    return 0


def _combined_caster_level(prog, thirds, classes) -> int:
    """RAW multiclass caster level — sum of every class's contribution, for any number of casters."""
    return sum(_caster_share(prog, thirds, *_unpack(c)) for c in classes)


def _slots_from(cat, ci, lv) -> dict:
    """{spell level: count} from a class's level table (non-zero only)."""
    return {int(k.rsplit("_", 1)[-1]): v for k, v in H._spellcasting(cat, ci, lv).items()
            if k.startswith("spell_slots_level_") and v}


def _thirds(cat) -> set:
    return {H._norm(s) for s in cat.get("third_caster_subclasses", [])}


def spell_slots(cat, classes) -> dict:
    """Spell slots by level via the RAW combined caster level — looked up in a full caster's slot table
    (a full caster's progression IS the multiclass table, so single-class casters are unchanged and
    half-casters reproduce exactly). Generic over any number of caster classes, incl. third-caster
    subclasses (EK/AT). Warlock pact slots are excluded here (see pact_slots)."""
    prog = cat.get("caster_progression", {})
    level = _combined_caster_level(prog, _thirds(cat), classes)
    ref = next((ci for ci in sorted(prog) if prog[ci] == "full"), None)
    return _slots_from(cat, ref, level) if level and ref else {}


def pact_slots(cat, classes) -> dict:
    """Warlock Pact Magic — a separate pool (N slots, all of one level). Summed over any pact classes."""
    prog = cat.get("caster_progression", {})
    out = {}
    for c in classes:
        ci, lv, _ = _unpack(c)
        if prog.get(ci) == "pact":
            for level, n in _slots_from(cat, ci, lv).items():
                out[level] = out.get(level, 0) + n
    return dict(sorted(out.items()))


# Choice fields (from the feature layer) that carry extra spells beyond the main spell_choices.
# These are always *known* (a feature grants them outright). Mirrors the field names in
# app.generation.features.
_FEATURE_CANTRIP_FIELDS = ("ek_cantrips", "at_cantrips", "bonus_cantrip", "nature_cantrip", "high_elf_cantrip")
_FEATURE_SPELL_FIELDS = ("ek_spells", "at_spells", "magical_secrets")


def _as_list(v):
    return [v] if isinstance(v, str) else list(v or [])


def spellbook(cat, choices) -> list:
    """Every spell the character has, bucketed by real level and de-duped. A leveled `spell_choices`
    spell is tagged **prepared** when it sits on one of the character's *prepared-caster* class lists
    (so a prepared+known multiclass tags each spell per the class that grants it), otherwise known.
    Feature-granted spells (EK/AT, bonus/nature/high-elf cantrips, bardic magical secrets) are always
    known; cantrips are always known."""
    sc = choices.get("spell_choices") or {}
    prepared_set = set(cat.get("prepared_casters") or [])
    char_prepared = {H._ci(c["class"]) for c in choices.get("classes", [])} & prepared_set
    spells = cat.records("spells").values()
    level_by_name = {s["name"]: s["level"] for s in spells}
    classes_by_name = {s["name"]: {c["index"] for c in s.get("classes", [])} for s in spells}

    def is_prepared(name):
        return bool(classes_by_name.get(name, set()) & char_prepared)

    out, seen = [], set()

    def add(name, level, prepared):
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "level": level, "prepared": prepared})

    for nm in sc.get("cantrips", []):
        add(nm, 0, False)
    for nm in sc.get("spells", []):
        lvl = level_by_name.get(nm)
        if lvl is not None:                  # drop an unknown name rather than guessing level 1
            add(nm, lvl, is_prepared(nm))
    for field in _FEATURE_CANTRIP_FIELDS:
        for nm in _as_list(choices.get(field)):
            add(nm, 0, False)
    for field in _FEATURE_SPELL_FIELDS:
        for nm in _as_list(choices.get(field)):
            lvl = level_by_name.get(nm)
            if lvl is not None:
                add(nm, lvl, False)
    return out
