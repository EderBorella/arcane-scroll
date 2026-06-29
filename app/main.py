"""Arcane Scroll API. Loads the catalog into memory at startup, exposes liveness/readiness, and
mounts the generation controller."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import catalog
from app.controllers import generation


@asynccontextmanager
async def lifespan(_: FastAPI):
    catalog.load()
    yield


app = FastAPI(title="Arcane Scroll", version="0.0.1", lifespan=lifespan)
app.include_router(generation.router)


@app.get("/health")
def health():
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness — the catalog is loaded into memory (proves the data mount works)."""
    try:
        cat = catalog.get_catalog()
        return {"ready": True, **cat.stats()}
    except Exception:                       # readiness must never throw — any failure means "not ready"
        return {"ready": False}
