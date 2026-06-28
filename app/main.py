"""Arcane Scroll API (skeleton). Loads the catalog into memory at startup and exposes liveness/
readiness. Generation endpoints come next."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import catalog

_state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    _state["catalog"] = catalog.load()
    yield
    _state.clear()


app = FastAPI(title="Arcane Scroll", version="0.0.1", lifespan=lifespan)


@app.get("/health")
def health():
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness — the catalog is loaded into memory (proves the data mount works)."""
    cat = _state.get("catalog")
    if cat is None:
        return {"ready": False}
    return {"ready": True, **cat.stats()}
