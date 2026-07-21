"""Generator-side choice seam (model-bound).

The DAL-grounded choice grammar itself is model-free and lives in the standalone rule engine
(``engine.choices``): ``parse_request`` -> the offered schema -> ``assemble`` -> the completeness
manifest. This package holds only the piece the generator owns: ``generate_choices``, the two-pass
model-call seam (``orchestrator.py``) that drives the model against the engine's grammar and folds
the picks together. It is model-bound (it reaches the model client), so it stays with the generator
service rather than the engine.
"""
from app.generation.choices.orchestrator import generate_choices  # noqa: F401  (re-exported)
