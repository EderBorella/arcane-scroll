"""HTTP controller for character generation. Thin: validate input, call the generator service,
return JSON. No business logic here — that lives in app.generation."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import catalog
from app.generation import generate_sheet, parse

router = APIRouter(prefix="/v1", tags=["generation"])


class CharacterRequest(BaseModel):
    race: str
    classes: list[dict]                       # [{"class": ..., "level": ...}, ...]
    subclasses: dict[str, str] = {}           # optional per-class overrides
    unique: str | None = None                 # the "what is unique about this character?" field


@router.post("/characters")
def create_character(req: CharacterRequest):
    """Generate a character's CHOICES from a request. (The full computed sheet — derivation — and a
    backstory generator come in following PRs; this returns the grammar-constrained, repaired choices.)"""
    cat = catalog.get_catalog()
    try:
        spec = parse(cat, req.model_dump())
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"choices": generate_sheet(cat, spec)}
