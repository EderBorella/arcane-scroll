"""HTTP controller for character generation. Thin: validate input, call the generator service,
return JSON. No business logic here — that lives in app.generation / engine.derivation. The request/
response models below are what FastAPI renders into the OpenAPI docs (`/docs`)."""
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from access.generator import GeneratorAccess
from access.generator import classes as class_q
from access.generator import species as species_q
from app.generation import generate_backstory
from app.generation.choices import generate_choices
from app.generation.client import ModelError
from engine.choices import parse_request
from engine.derivation.document import derive_document

router = APIRouter(prefix="/v1", tags=["generation"])


class ClassEntry(BaseModel):
    """One class the character has levels in. Multiple entries = multiclass."""
    model_config = ConfigDict(populate_by_name=True)

    class_: str = Field(alias="class", description="Class id (lowercase).")
    level: int = Field(ge=1, le=20, description="Levels in this class (1–20).")


class CharacterRequest(BaseModel):
    species: str = Field(description="Species id (resolved against the loaded ruleset).")
    classes: list[ClassEntry] = Field(min_length=1,
                                       description="One entry per class; more than one = multiclass.")
    subclasses: dict[str, str] = Field(
        default_factory=dict,
        description="Optional subclass override, keyed by class id (value = subclass id). "
                    "Any class left out gets a random valid subclass once its level unlocks one.")
    background: str | None = Field(
        default=None,
        description="Optional background id. If omitted, no background is applied (no background "
                    "ability boost or origin feat).")
    alignment: str | None = Field(
        default=None,
        description="Optional alignment id.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"species": "<species>", "classes": [{"class": "<class>", "level": 5}]},
        {"species": "<species>",
         "classes": [{"class": "<class>", "level": 3}, {"class": "<class>", "level": 2}]},
    ]})


@router.post("/characters",
             summary="Generate a character document (five-schema, contract-conformant)",
             description=(
                 "Turn a request (species + class(es), optional per-class subclass overrides, "
                 "optional background) into a complete character document: the CORE sheet plus "
                 "INVENTORY, an optional GRIMOIRE (class spellcasters), the MODIFIER (live/effective) "
                 "layer, and an optional COMPANION block. The document shape is "
                 "`{core, inventory, grimoire?, modifier, companion?}`, each part conforming to its "
                 "live sub-schema. Species / class / level / subclass / background are code-resolved "
                 "against the loaded ruleset. **400** = unknown id or out-of-range level; **502** = "
                 "model backend error."))
def create_character(req: CharacterRequest) -> dict:
    access = GeneratorAccess()
    payload = {
        "species": req.species,
        "classes": [{"class": c.class_, "level": c.level} for c in req.classes],
        "subclasses": req.subclasses,
        "background": req.background,
        "character_id": uuid.uuid4().hex,   # server-assigned identity for this generated character
        "alignment": req.alignment,
    }
    try:
        try:
            spec = parse_request(access, payload)
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        try:
            choices = generate_choices(access, spec)
            return derive_document(choices, access)
        except ModelError as e:
            raise HTTPException(status_code=502, detail=f"model backend error: {e}")
    finally:
        access.db.close()   # close on every path (400/502/success), not just the guarded block


class BackstoryRequest(BaseModel):
    character: dict = Field(
        description="A character's choices (as returned by /v1/characters); needs at least "
                    "'species' (a species id) and 'classes'. More fields (name, alignment, "
                    "background, spells) give the backstory more to work with.")
    unique: str | None = Field(
        default=None,
        description="Optional 'what is unique about this character?' hint. If omitted, a random "
                    "angle is used so backstories stay varied.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"character": {"species": "<species>", "classes": [{"class": "<class>", "level": 5}],
                       "name": "<name>", "background": "<background>"},
         "unique": "<optional flavour hint>"},
    ]})


class BackstoryResponse(BaseModel):
    """The flavour bundle: physical traits, personality (traits/ideal/bond/flaw), and a backstory."""
    flavour: dict


@router.post("/backstory", response_model=BackstoryResponse,
             summary="Generate a character's flavour (backstory bundle)",
             description=(
                 "Given a character's choices, generate physical traits (bounded by the character's "
                 "origin), personality (two traits + ideal/bond/flaw), and a short backstory — "
                 "grounded in the sheet. Physical bounds are clamped server-side. **400** if the "
                 "character lacks a species or classes."))
def create_backstory(req: BackstoryRequest) -> BackstoryResponse:
    access = GeneratorAccess()
    try:
        character = dict(req.character)
        species_id, classes = character.get("species"), character.get("classes")
        if not species_id or not classes:
            raise HTTPException(status_code=400,
                                detail="character must include 'species' and 'classes'")
        # validate against the DAL (the current species model) so a garbage species/class never
        # reaches the model
        if species_id not in {r["id"] for r in species_q.list_species(access)}:
            raise HTTPException(status_code=400, detail=f"unknown species: {species_id!r}")
        class_ids = {r["id"] for r in class_q.list_classes(access)}
        for c in classes:
            if c.get("class") not in class_ids:
                raise HTTPException(status_code=400, detail=f"unknown class: {c.get('class')!r}")
        if req.unique:
            character["unique"] = req.unique
        try:
            return BackstoryResponse(flavour=generate_backstory(access, character))
        except ModelError as e:
            raise HTTPException(status_code=502, detail=f"model backend error: {e}")
    finally:
        access.db.close()
