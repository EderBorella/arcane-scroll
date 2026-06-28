"""Generation layer — one module per generator over shared helpers.

Generators:
  - sheet      character sheet (this PR)
  - backstory  flavour bundle  (next PR — its own module + helpers, in the same shape)

Shared: helpers.py (pure compute), client.py (model I/O), request.py (request parsing)."""
from app.generation.request import Spec, parse  # noqa: F401  (re-exported)
from app.generation.sheet import generate as generate_sheet  # noqa: F401  (re-exported)
