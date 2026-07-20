"""Generator service API — character generation, plus liveness/readiness.

The generator is the ONLY service that talks to the model. It reads rule facts from the read-only
reference DB via $ARCANE_RULES_DB (opened per request in the DAL, the same DB wiring the validator
uses). No other service depends on the model.
"""
from fastapi import FastAPI

from access.db import RulesDB
from app.controllers import generation

app = FastAPI(title="character generator", version="0.0.1")
app.include_router(generation.router)


@app.get("/health")
def health() -> dict:
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    """Readiness — the read-only reference DB is reachable (proves the rules.db mount + env)."""
    try:
        with RulesDB() as db:            # path from $ARCANE_RULES_DB; raises clearly if unset
            db.scalar("SELECT 1")
        return {"ready": True}
    except Exception:                    # readiness must never throw — any failure means "not ready"
        return {"ready": False}
