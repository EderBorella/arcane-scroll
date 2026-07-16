"""The two-pass generation seam — turn a validated build spec into a full ``choices`` object,
grounded in the DAL and shaped for the derivation pipeline.

The model-call seam kept from the original generator is preserved: pass 1 builds the sheet minus
starting equipment; pass 2 builds the starting-equipment bundle (skipped when the build has no bundle
grammar). Each pass is grammar-constrained — the grammar (grammar.py) says what the model may pick,
the model picks, and the assembler (assemble.py) folds the picks together with the code-decided
fields. The model call is injected as ``pick(prompt, schema) -> dict`` so a caller can drive it with a
real backend or seed it deterministically (tests, reproducible builds) without a live model.

The HTTP generation endpoint (``app.controllers.generation``) drives this seam with the default
``pick`` (the live model client) and returns the assembled document; a test stubs ``pick`` to seed
picks. The prompt (``_prompt``) is a content-neutral ChatML build brief resolved from the loaded
ruleset — no game literals live here.
"""
import random

from access.generator import catalog
from app.generation import client
from app.generation.choices import assemble, grammar, options


def _default_pick(prompt, schema):
    """The live model call used by the HTTP endpoint. Tests inject their own ``pick`` to seed picks
    deterministically without a live model."""
    return client.generate(prompt, schema)


def generate_choices(access, spec, *, pick=_default_pick, rng=random, feat_slots=None):
    """Run the two-pass grammar for ``spec`` and return the canonical ``choices``. ``access`` is a
    ``GeneratorAccess``; ``pick(prompt, schema)`` performs the model call (inject a stub to seed
    picks deterministically). ``feat_slots`` is the number of ability-increase/feat slots the build
    offers; left at None it is derived from the per-class slot progression in the reference data
    (``options.ability_feat_slot_count``), so a level-4+ build reaches its ability-increase/feat
    choices. A caller may pin an explicit count (e.g. a deterministic test)."""
    resolved = [(cid, lv, options.resolve_subclass(access, cid, lv, spec.subclasses.get(cid), rng))
                for cid, lv in spec.classes]
    if feat_slots is None:
        feat_slots = options.ability_feat_slot_count(access, resolved)

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
    """The ChatML model prompt for one generation pass, grounded in the resolved build. Display names
    resolve from the loaded ruleset (data, not literals) — no game vocabulary is baked in here. Pass
    ``"sheet"`` asks the model to build the character; pass ``"equipment"`` asks it to pick starting
    gear. A caller that stubs ``pick`` never sees this."""
    species = catalog.name_of(access, "species", spec.species) or spec.species
    desc = " / ".join(
        f"{catalog.name_of(access, 'class', cid) or cid} {lv}"
        + (f" ({catalog.name_of(access, 'subclass', sub)})" if sub else "")
        for cid, lv, sub in resolved)
    build = f"{species} {desc}"
    bg_name = catalog.name_of(access, "background", spec.background) if spec.background else None
    if bg_name:
        build += f", background {bg_name}"

    if pass_name == "equipment":
        system = ("You choose a character's starting equipment. Pick options that fit the build. "
                  "Answer only with the requested fields.")
        task = f"Choose starting equipment for: {build}."
    else:
        system = ("You build a character. Choose only from the offered options and answer only with "
                  "the requested fields.")
        task = f"Build this character: {build}."
    return (f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{task}<|im_end|>\n<|im_start|>assistant\n")
