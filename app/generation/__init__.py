"""Generation layer — one module per generator over shared helpers.

Generators:
  - sheet      character sheet (choices)
  - backstory  flavour bundle (physical + personality + backstory)

Shared: helpers.py (pure compute), client.py (model I/O), request.py (request parsing)."""
from app.generation.backstory import generate as generate_backstory  # noqa: F401  (re-exported)
from app.generation.request import Spec, parse  # noqa: F401  (re-exported)
from app.generation.sheet import generate as generate_sheet  # noqa: F401  (re-exported)
