"""The two-pass generation seam — turn a validated build spec into a full ``choices`` object,
grounded in the DAL and shaped for the derivation pipeline.

The model-call seam kept from the original generator is preserved: pass 1 builds the sheet minus
starting equipment; pass 2 builds the starting-equipment bundle (skipped when the build has no bundle
grammar). Each pass is grammar-constrained — the grammar (grammar.py) says what the model may pick,
the model picks, and the assembler (assemble.py) folds the picks together with the code-decided
fields. The model call is injected as ``pick(prompt, schema) -> dict`` so a caller can drive it with a
real backend or seed it deterministically (tests, reproducible builds) without a live model.
"""
import random

from access.generator import catalog
from app.generation import client
from app.generation.choices import assemble, grammar, options


def _default_pick(prompt, schema):
    """The live model call. (Wiring the HTTP generation endpoint onto this seam — building the full
    prompt and cutting the controller over — is Phase-5; today callers inject their own ``pick``.)"""
    return client.generate(prompt, schema)


def generate_choices(access, spec, *, pick=_default_pick, rng=random, feat_slots=0):
    """Run the two-pass grammar for ``spec`` and return the canonical ``choices``. ``access`` is a
    ``GeneratorAccess``; ``pick(prompt, schema)`` performs the model call (inject a stub to seed
    picks deterministically). ``feat_slots`` is the number of ability-increase/feat slots the build
    has reached (0 by default — the per-class slot progression is Phase-5, so callers pass it in)."""
    resolved = [(cid, lv, options.resolve_subclass(access, cid, lv, spec.subclasses.get(cid), rng))
                for cid, lv in spec.classes]

    schema1 = grammar.build_pass1_grammar(access, spec, resolved, feat_slots=feat_slots)
    picks1 = pick(_prompt(access, spec, resolved, "sheet"), schema1) or {}
    choices = assemble.assemble_choices(access, spec, resolved, picks1, feat_slots=feat_slots)

    schema2 = grammar.build_equipment_grammar(access, spec, resolved)
    if schema2.get("properties"):
        picks2 = pick(_prompt(access, spec, resolved, "equipment"), schema2) or {}
        assemble.apply_equipment(access, spec, resolved, picks2, choices)
    else:
        choices["equipment"] = {"equipped": {}, "backpack": []}
    return choices


def _prompt(access, spec, resolved, pass_name):
    """A minimal, content-neutral build summary for the model call. Display names resolve from the
    loaded ruleset (data, not literals). A caller that stubs ``pick`` never sees this; the full
    prompt for the live endpoint is Phase-5."""
    species = catalog.name_of(access, "species", spec.species) or spec.species
    desc = " / ".join(
        f"{catalog.name_of(access, 'class', cid) or cid} {lv}"
        + (f" ({catalog.name_of(access, 'subclass', sub)})" if sub else "")
        for cid, lv, sub in resolved)
    return f"pass={pass_name}; build={species} {desc}"
