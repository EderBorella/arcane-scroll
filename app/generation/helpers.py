"""Pure, catalog-driven helpers for the generator: compute the *resources* a request needs
(ability assignment, skill options, spell pools, subclass resolution) and repair the model's output.

The model picks; these compute. Every function takes the catalog (and inputs) as arguments and
returns a value — no globals, no side-effects — so each is unit-testable in isolation. Mechanics
live here in code; the value-lists come from the catalog by neutral key.
"""
import random
import re


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _ci(name) -> str:
    return re.sub(r"\s+", "", str(name).lower())


# ── abilities ────────────────────────────────────────────────────────────────
def ability_assignment(cat, primary_class: str) -> dict:
    """The standard array assigned to abilities by the class's priority order (pre-racial)."""
    order = cat.get("ability_priority").get(primary_class) or cat.get("abilities")
    desc = sorted(cat.get("standard_array"), reverse=True)
    return {ab: desc[i] for i, ab in enumerate(order)}


def race_bonus(cat, race: str, ability: str) -> int:
    """Racial + subracial bonus to one ability (base race + subrace records + supplemental table)."""
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    races, subraces = cat.records("races"), cat.records("subraces")
    recs = []
    if idx in subraces:
        recs.append(subraces[idx])
        parent = subraces[idx].get("race", {}).get("index")
        if parent in races:
            recs.append(races[parent])
    elif idx in races:
        recs.append(races[idx])
    else:
        for base in races:
            if base in idx:
                recs.append(races[base])
                break
    total = sum(ab["bonus"] for r in recs for ab in r.get("ability_bonuses", [])
                if ab["ability_score"]["index"] == ability)
    return total + cat.get("subrace_bonus", {}).get(idx, {}).get(ability, 0)


# ── skills ───────────────────────────────────────────────────────────────────
def class_skill_grant(cat, ci: str):
    """(count, {skill indices}) the class chooses its skill proficiencies from."""
    c = cat.record("classes", ci)
    if not c:
        return (0, set())
    for pc in c.get("proficiency_choices", []):
        opts = {o.get("item", {}).get("index", "")[6:] for o in pc.get("from", {}).get("options", [])
                if o.get("item", {}).get("index", "").startswith("skill-")}
        if opts:
            return (pc.get("choose", 0), opts)
    return (0, set())


def skill_names(cat, indices) -> list:
    """Display names for skill indices, sorted."""
    skills = cat.records("skills")
    return sorted(skills[i]["name"] for i in indices if i in skills)


# ── spellcasting (from the per-level tables) ─────────────────────────────────
def _spellcasting(cat, ci: str, lv: int) -> dict:
    for rec in cat.records("levels").values():
        if rec.get("class", {}).get("index") == ci and rec.get("level") == lv:
            return rec.get("spellcasting") or {}
    return {}


def cantrips_known(cat, ci, lv):
    return _spellcasting(cat, ci, lv).get("cantrips_known", 0)


def spells_known(cat, ci, lv):
    return _spellcasting(cat, ci, lv).get("spells_known")


def has_slots(cat, ci, lv) -> bool:
    sc = _spellcasting(cat, ci, lv)
    return any(v for k, v in sc.items() if k.startswith("spell_slots_level_"))


def max_spell_level(cat, ci, lv) -> int:
    sc = _spellcasting(cat, ci, lv)
    lvls = [int(k.rsplit("_", 1)[-1]) for k, v in sc.items() if k.startswith("spell_slots_level_") and v]
    return max(lvls) if lvls else 0


# ── spells ───────────────────────────────────────────────────────────────────
def class_spells(cat, ci: str, max_lv: int, cantrip: bool) -> list:
    """Spell names available to a class: cantrips, or leveled spells up to max_lv."""
    out = []
    for s in cat.records("spells").values():
        if ci not in {c["index"] for c in s.get("classes", [])}:
            continue
        if cantrip and s["level"] == 0:
            out.append(s["name"])
        elif not cantrip and 1 <= s["level"] <= max_lv:
            out.append(s["name"])
    return sorted(set(out))


def caster_classes(cat, classes) -> list:
    """[(ci, lv)] of the classes that can cast at their level."""
    return [(ci, lv) for ci, lv in classes if has_slots(cat, ci, lv) or cantrips_known(cat, ci, lv)]


def _patron_expanded(cat, resolved, max_lv) -> set:
    """Patron-expanded spells become choosable for a warlock with a resolved subclass."""
    out, expanded = set(), cat.get("patron_expanded", {})
    for ci, lv, sub in resolved:
        if ci == "warlock" and sub:
            for slot_lv, names in expanded.get(_norm(sub), {}).items():
                if int(slot_lv) <= max_lv:
                    out.update(names)
    return out


def spell_pools(cat, resolved, race, ability_assign):
    """(cantrip_pool, spell_pool, n_cantrips, n_spells) for the caster classes, or None for non-casters.
    resolved: [(ci, lv, subclass_or_None)]."""
    casters = [(ci, lv) for ci, lv, _ in resolved if has_slots(cat, ci, lv) or cantrips_known(cat, ci, lv)]
    if not casters:
        return None
    known, prepared = set(cat.get("known_casters")), set(cat.get("prepared_casters"))
    gmax = max(max_spell_level(cat, ci, lv) for ci, lv in casters)
    cantrip_pool = sorted(set().union(*[set(class_spells(cat, ci, 0, True)) for ci, lv in casters]))
    spell_pool = set().union(*[set(class_spells(cat, ci, gmax, False)) for ci, lv in casters])
    spell_pool |= _patron_expanded(cat, resolved, gmax)
    spell_pool = sorted(spell_pool)

    n_cant = min(sum(cantrips_known(cat, ci, lv) or 0 for ci, lv in casters), len(cantrip_pool))
    n_spell = 0
    for ci, lv in casters:
        if ci in known:
            n_spell += spells_known(cat, ci, lv) or 0
        elif ci in prepared:
            ab = cat.record("classes", ci)["spellcasting"]["spellcasting_ability"]["index"]
            mod = ((ability_assign[ab] + race_bonus(cat, race, ab)) - 10) // 2
            n_spell += max(1, mod + (lv // 2 if ci == "paladin" else lv))
    n_spell = min(max(n_spell, 1), len(spell_pool))
    return cantrip_pool, spell_pool, n_cant, n_spell


# ── subclass resolution (code picks, before the model call) ──────────────────
def resolve_subclasses(cat, classes, overrides=None, rng=random) -> list:
    """One subclass per class, aligned to `classes` (None where the level hasn't unlocked it):
    user override if given, else random from the class's options."""
    overrides = {_ci(k): v for k, v in (overrides or {}).items()}
    options, levels = cat.get("subclass_options", {}), cat.get("subclass_level", {})
    out = []
    for ci, lv in classes:
        if ci in options and lv >= levels.get(ci, 99):
            out.append(overrides.get(ci) or rng.choice(options[ci]))
        else:
            out.append(None)
    return out


# ── repair (engine step: dedup + pad to the granted counts) ──────────────────
def _dedup_pad(chosen, pool, n) -> list:
    pool_norm = {_norm(p) for p in pool}
    out, seen = [], set()
    for x in chosen:
        nx = _norm(x)
        if nx in pool_norm and nx not in seen:
            out.append(x)
            seen.add(nx)
    for p in pool:
        if len(out) >= n:
            break
        if _norm(p) not in seen:
            out.append(p)
            seen.add(_norm(p))
    return out[:n]


def repair(cat, choices, race, classes, subclasses):
    """De-dup + pad skill/spell picks to the granted counts (a grammar can't enforce uniqueness)."""
    primary = classes[0][0]
    n_skill, skill_idx = class_skill_grant(cat, primary)
    choices["skill_choices"] = _dedup_pad(choices.get("skill_choices", []), skill_names(cat, skill_idx), n_skill)
    resolved = [(ci, lv, sub) for (ci, lv), sub in zip(classes, subclasses)]
    pools = spell_pools(cat, resolved, race, ability_assignment(cat, primary))
    if pools and choices.get("spell_choices"):
        cant, spl, nc, ns = pools
        sc = choices["spell_choices"]
        sc["cantrips"] = _dedup_pad(sc.get("cantrips", []), cant, nc)
        sc["spells"] = _dedup_pad(sc.get("spells", []), spl, ns)
    return choices


# ── backstory / flavour helpers ──────────────────────────────────────────────
_DEFAULT_PHYS = {"age": [16, 100], "h": [48, 84], "w": [80, 320]}


def physical_bounds(cat, race: str):
    """((age_min, age_max), (h_min, h_max), (w_min, w_max)) for a race, with a generic fallback."""
    p = cat.get("race_phys", {}).get(race) or _DEFAULT_PHYS
    return tuple(p["age"]), tuple(p["h"]), tuple(p["w"])


def skin_options(cat, race: str) -> list:
    """Skin enum for a race — a race-specific override if present, else the default palette."""
    return cat.get("skin_overrides", {}).get(race) or cat.get("skin_default")


def character_summary(character: dict) -> str:
    """A one-line sheet summary to ground the backstory in (name / race / class(es) / bg / picks)."""
    cl = " / ".join(f"{c.get('class')} {c.get('level')}" + (f" ({c['subclass']})" if c.get("subclass") else "")
                    for c in character.get("classes", []))
    s = f"{character.get('name', '')}, a {character.get('race', '')} {cl}.".strip()
    if character.get("alignment"):
        s += f" Alignment: {character['alignment']}."
    if character.get("background"):
        s += f" Background: {character['background']}."
    if character.get("skill_choices"):
        s += f" Skills: {', '.join(character['skill_choices'])}."
    spells = (character.get("spell_choices") or {}).get("spells")
    if spells:
        s += f" Spells: {', '.join(spells)}."
    return s


def clamp_physical(cat, race: str, flavour: dict) -> dict:
    """Clamp age/height/weight into the race's bounds (a grammar can't enforce numeric ranges)."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = physical_bounds(cat, race)
    for key, lo, hi in (("age", amin, amax), ("height_inches", hmin, hmax), ("weight_lbs", wmin, wmax)):
        v = flavour.get(key)
        if isinstance(v, (int, float)):
            flavour[key] = max(lo, min(hi, int(v)))
    return flavour
