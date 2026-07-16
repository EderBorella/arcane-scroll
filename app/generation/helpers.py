"""Pure, catalog-driven helpers for the backstory (flavour) generator: physical bounds, skin palette,
a one-line sheet summary, and the physical-clamp. Plus the two name normalisers the generation
controller uses to validate an incoming character against the catalog.

The model picks; these compute. Every function takes the catalog (and inputs) as arguments and
returns a value — no globals, no side-effects — so each is unit-testable in isolation.
"""
import re


# Two deliberately different normalisers, by key type:
#   _norm — strips ALL non-alphanumerics; for display-name comparisons ("Half-Elf" == "half elf").
#   _ci  — strips only whitespace; for class *indices* which keep hyphens ("eldritch-knight").
# Don't merge them: _norm would collapse "eldritch-knight" → "eldritchknight" and break index lookups.
def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _ci(name) -> str:
    return re.sub(r"\s+", "", str(name).lower())


def _by_norm(table: dict, key):
    """Look a value up in a display-name-keyed table, tolerating casing/punctuation differences."""
    if key in table:
        return table[key]
    nk = _norm(key)
    return next((v for k, v in table.items() if _norm(k) == nk), None)


# ── backstory / flavour helpers ──────────────────────────────────────────────
_DEFAULT_PHYS = {"age": [16, 100], "h": [48, 84], "w": [80, 320]}


def physical_bounds(cat, race: str):
    """((age_min, age_max), (h_min, h_max), (w_min, w_max)) for an origin, with a generic fallback.
    The key is matched casing/punctuation-tolerantly (the /backstory path doesn't canonicalise it)."""
    p = _by_norm(cat.get("race_phys", {}), race) or _DEFAULT_PHYS
    return tuple(p["age"]), tuple(p["h"]), tuple(p["w"])


def skin_options(cat, race: str) -> list:
    """Skin enum for an origin — an origin-specific override if present, else the default palette."""
    return _by_norm(cat.get("skin_overrides", {}), race) or cat.get("skin_default")


def character_summary(character: dict) -> str:
    """A one-line sheet summary to ground the backstory in (name / origin / class(es) / bg / picks)."""
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
    """Clamp age/height/weight into the origin's bounds (a grammar can't enforce numeric ranges)."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = physical_bounds(cat, race)
    for key, lo, hi in (("age", amin, amax), ("height_inches", hmin, hmax), ("weight_lbs", wmin, wmax)):
        v = flavour.get(key)
        if isinstance(v, (int, float)):
            flavour[key] = max(lo, min(hi, int(v)))
    return flavour
