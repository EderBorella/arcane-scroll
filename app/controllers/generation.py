"""HTTP controller for character generation. Thin: validate input, call the generator service,
return JSON. No business logic here — that lives in app.generation. The request/response models
below are what FastAPI renders into the OpenAPI docs (`/docs`)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import catalog
from app.generation import generate_sheet, parse

router = APIRouter(prefix="/v1", tags=["generation"])


class ClassEntry(BaseModel):
    """One class the character has levels in. Multiple entries = multiclass."""
    model_config = ConfigDict(populate_by_name=True)

    class_: str = Field(alias="class", description="Class index (lowercase).")
    level: int = Field(ge=1, le=20, description="Levels in this class (1–20).")


class CharacterRequest(BaseModel):
    race: str = Field(description="Race or subrace name.")
    classes: list[ClassEntry] = Field(min_length=1,
                                      description="One entry per class; more than one = multiclass.")
    subclasses: dict[str, str] = Field(
        default_factory=dict,
        description="Optional subclass override, keyed by class index (value = subclass name). "
                    "Any class left out gets a random valid subclass once its level unlocks one.")
    unique: str | None = Field(
        default=None,
        description="Optional free-text 'what is unique about this character?' hint that steers flavour.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"race": "<race>", "classes": [{"class": "<class>", "level": 5}]},
        {"race": "<race>",
         "classes": [{"class": "<class>", "level": 3}, {"class": "<class>", "level": 2}],
         "unique": "<optional flavour hint>"},
    ]})


class CharacterResponse(BaseModel):
    """The generated **choices** — what the model picked plus the code-injected deterministic fields.
    (The full computed sheet comes once the derivation engine lands.)"""
    choices: dict


@router.post("/characters", response_model=CharacterResponse,
             summary="Generate a character's choices",
             description=(
                 "Turn a request (race + class(es), optional per-class subclass overrides, optional "
                 "uniqueness hint) into a character's grammar-constrained, repaired **choices**: "
                 "name, background, alignment, ability assignment, skills, and spells (when a caster). "
                 "Race / class / level / subclass are code-resolved; the rest the model picks within "
                 "the per-request grammar. **400** = unknown race/class or out-of-range level.\n\n"
                 "_The full computed sheet (derivation) and a separate backstory endpoint come in later PRs._"))
def create_character(req: CharacterRequest) -> CharacterResponse:
    cat = catalog.get_catalog()
    try:
        spec = parse(cat, req.model_dump(by_alias=True))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CharacterResponse(choices=generate_sheet(cat, spec))
