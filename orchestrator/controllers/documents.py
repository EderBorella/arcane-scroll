"""Document controllers — thin HTTP adapters for the derive / validate-document flows (F07 D5/D6).

Controllers hold NO business logic (Controller -> Orchestrator -> Services): they translate HTTP to
an Orchestrator call and map errors to status codes. The composition — parse, assemble, derive,
validate, report — lives on the Orchestrator.
"""
from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter(tags=["documents"])


@router.post("/v1/derive",
             summary="Derive a character document + completeness report from a minimal build spec",
             description=(
                 "Stateless, deterministic, NO-model derive. Body = a build spec: `species`, "
                 "`classes` (each `{class, level}`), optional per-class `subclasses`, optional "
                 "`background` / `alignment`, and an optional `choices` object of explicit picks. "
                 "Returns `{document, report}` — the `character-document` envelope and the "
                 "`completeness-report`. Same input always yields the same output. **400** = a "
                 "missing or unknown fundamental (species / class / subclass / level / background)."))
def derive(request: Request, req: dict = Body(...)) -> dict:
    orchestrator = request.app.state.orchestrator
    try:
        return orchestrator.derive(req)
    except (ValueError, KeyError, TypeError) as e:
        # Fail-fast on a missing / malformed fundamental — parse_request raises before any derivation.
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate-document",
             summary="Validate a character-document envelope and return one completeness report",
             description=(
                 "Body = a `character-document` envelope (`core` required; `inventory` / `grimoire` / "
                 "`modifier` / `companion` optional). Runs the per-sheet validators over the present "
                 "sheets, folds them into one verdict, and adds the typed completeness manifest. "
                 "Returns the `completeness-report`."))
def validate_document(request: Request, req: dict = Body(...)) -> dict:
    orchestrator = request.app.state.orchestrator
    try:
        return orchestrator.validate_document(req)
    except (ValueError, KeyError, TypeError) as e:
        # A shape-malformed envelope (e.g. a non-object sheet) surfaces as a 400, not a 500.
        raise HTTPException(status_code=400, detail=str(e))
