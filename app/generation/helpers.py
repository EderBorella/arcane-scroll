"""Pure helpers for the backstory (flavour) generator: physical bounds, appearance-palette selection,
a one-line sheet summary, and the physical-clamp.

The model picks; these compute. Every function takes the DAL access handle (and inputs) and returns a
value — no globals, no side-effects — so each is unit-testable in isolation. The flavour data itself
(bounds, palettes) is read from the reference DB via the generator access layer.
"""
from access.generator import flavour as F

# Generic physical fallback for a species that carries no bounds row in the reference data —
# ((age_min, age_max), (height_min, height_max), (weight_min, weight_max)).
_DEFAULT_PHYS = ((16, 100), (48, 84), (80, 320))


def physical_bounds(access, species_id: str | None):
    """((age_min, age_max), (h_min, h_max), (w_min, w_max)) for a species, with a generic fallback
    for a species that carries no bounds row."""
    row = F.physical_bounds(access, species_id)
    if row is None:
        return _DEFAULT_PHYS
    return ((row["age_min"], row["age_max"]),
            (row["height_min"], row["height_max"]),
            (row["weight_min"], row["weight_max"]))


def appearance_options(access, axis: str, species_id: str | None) -> list:
    """The enum for an appearance axis (gender/eyes/hair/skin): a species's override palette if it has
    one, else the shared default palette."""
    return F.appearance_overrides(access, axis, species_id) or F.appearance_defaults(access, axis)


def character_summary(character: dict, species_name: str) -> str:
    """A one-line sheet summary to ground the backstory in (name / species / class(es) / bg / picks)."""
    cl = " / ".join(f"{c.get('class')} {c.get('level')}" + (f" ({c['subclass']})" if c.get("subclass") else "")
                    for c in character.get("classes", []))
    s = f"{character.get('name', '')}, a {species_name} {cl}.".strip()
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


def clamp_physical(access, species_id: str | None, flavour: dict) -> dict:
    """Clamp age/height/weight into the species's bounds (a grammar can't enforce numeric ranges)."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = physical_bounds(access, species_id)
    for key, lo, hi in (("age", amin, amax), ("height_inches", hmin, hmax), ("weight_lbs", wmin, wmax)):
        v = flavour.get(key)
        if isinstance(v, (int, float)):
            flavour[key] = max(lo, min(hi, int(v)))
    return flavour
