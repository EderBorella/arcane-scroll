"""System controller — thin HTTP adapter for liveness/readiness.

No business logic lives here: the controller only translates HTTP <-> the Orchestrator
(Controller -> Orchestrator -> Services). Readiness delegates to the Orchestrator so the seam is
established for the derive / validate-document deliverables (F07 D5/D6).
"""
from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness — the process is up."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> dict:
    """Readiness — delegates to the Orchestrator; the controller holds no logic of its own."""
    orchestrator = request.app.state.orchestrator
    try:
        return orchestrator.ready()
    except Exception:            # readiness must never throw — any failure means "not ready"
        return {"ready": False}
