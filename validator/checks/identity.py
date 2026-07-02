"""Layer: identity. The chosen size is one the species allows, and the creature type matches the
species. Grounded in the species data; when the species isn't known there is nothing to check against,
so the layer stays silent (never guesses)."""
from validator.report import Violation

LAYER = "identity"


def check(sheet, rules):
    out = []
    ident = sheet.get("identity") or {}
    species = ident.get("species")
    if not rules.is_known_species(species):
        return out

    sizes = rules.species_sizes(species) or []
    size = ident.get("size")
    if sizes and size is not None and str(size).lower() not in [s.lower() for s in sizes]:
        out.append(Violation(LAYER, "illegal_size",
                             f"size '{size}' is not one the species '{species}' allows (allowed: {sizes})",
                             sizes, size))

    ct_exp = rules.species_creature_type(species)
    ct = ident.get("creature_type")
    if ct_exp is not None and ct is not None and str(ct).lower() != ct_exp.lower():
        out.append(Violation(LAYER, "creature_type_mismatch",
                             f"creature type '{ct}' does not match species '{species}' type '{ct_exp}'",
                             ct_exp, ct))
    return out
