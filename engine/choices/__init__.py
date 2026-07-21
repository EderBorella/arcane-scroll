"""DAL-grounded choice grammar (model-free).

Enumerates the choice space from the generator data-access layer (``access/generator``) and produces
the ``choices`` structure the derivation pipeline (``engine.derivation.document.derive_document``)
consumes — canonical DB ids throughout, a species with no ability bonus, and background-sourced
ability boosts + origin feat.

Everything here is pure: it builds the offered schema, parses a request, assembles validated picks,
and emits the completeness manifest — no model call lives in this package. The two-pass model-call
seam (``generate_choices``) is model-bound and stays with the generator service
(``app.generation.choices``).
"""
from engine.choices.manifest import awaiting_choices, build_manifest  # noqa: F401  (re-exported)
from engine.choices.spec import RequestSpec, parse_request  # noqa: F401  (re-exported)
