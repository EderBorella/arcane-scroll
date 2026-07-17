"""Neutral shared constants for the access layer.

Small, content-neutral identifiers shared by both the derivation engine and the
validator checks. They live here — in the access layer both sides already depend
on — so neither the deriver imports from the validator nor vice versa
(the T78/T96 independence rule)."""

# Abbreviation key for the resilience/hit-point ability score, as stored in the
# reference dataset's ability dimension. Used by HP re-derivation on both sides.
CON_ABBREV = "con"
