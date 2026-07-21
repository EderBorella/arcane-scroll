"""Model-free rule engine — the standalone package that turns a character's choices into the
five-schema document, with no model dependency.

Two subpackages:
  - ``engine.choices``     the DAL-grounded choice grammar: enumerate the offered choice space,
                           parse a request, assemble validated picks, and emit the completeness
                           manifest (all pure — no model call).
  - ``engine.derivation``  the derivation pipeline that computes the five-schema document from a
                           character's choices.

The engine reads only the data-access layer (``access/*``, pure DB reads). It never imports the
model client, the generator service (``app/*``), the validator checks (``validator/*``), or the
orchestrator — so a caller that must not touch the model (the orchestrator service) can compose the
engine directly, while the generator service keeps the model isolated behind its own package.
"""
