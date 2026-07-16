"""DAL-grounded choice grammar.

Enumerates the choice space from the generator data-access layer (``access/generator``) and produces
the ``choices`` structure the derivation pipeline (``app.derivation.document.derive_document``)
consumes — canonical DB ids throughout, a species with no ability bonus, and background-sourced
ability boosts + origin feat. ``generate_choices`` is the two-pass model-call seam.
"""
from app.generation.choices.orchestrator import generate_choices  # noqa: F401  (re-exported)
from app.generation.choices.spec import RequestSpec, parse_request  # noqa: F401  (re-exported)
