"""Orchestrator service — the front for F07's document endpoints, following the
Controller -> Orchestrator -> Services topology.

It builds the Orchestrator (the sole integrator) at startup and mounts the thin controller layer. It
depends on NO model: the model is reachable only via the generator service. The derive / validate-
document routes land in F07 D5/D6; this is the skeleton (system routes only).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from orchestrator.controllers import system
from orchestrator.orchestrator import Orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.orchestrator = Orchestrator()
    yield


app = FastAPI(title="character document orchestrator", version="0.0.1", lifespan=lifespan)
app.include_router(system.router)
