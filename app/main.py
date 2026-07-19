"""Arcane Scroll API. Exposes liveness/readiness and mounts the generation controller. Data is read
from the reference dataset through the access layer per request — there is no startup preload."""
from fastapi import FastAPI

from access.generator import GeneratorAccess
from access.generator import catalog
from app.controllers import generation


app = FastAPI(title="Arcane Scroll", version="0.0.1")
app.include_router(generation.router)


@app.get("/health")
def health():
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness — the reference data is reachable (proves the data mount works). Opens a short-lived
    access handle and reads a small, always-present enumeration; closes it on every path."""
    try:
        access = GeneratorAccess()
        try:
            abilities = len(catalog.list_abilities(access))
        finally:
            access.db.close()
        return {"ready": True, "abilities": abilities}
    except Exception:                       # readiness must never throw — any failure means "not ready"
        return {"ready": False}
