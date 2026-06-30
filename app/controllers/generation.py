"""HTTP controller for character generation. Thin: validate input, call the generator service,
return JSON. No business logic here — that lives in app.generation. The request/response models
below are what FastAPI renders into the OpenAPI docs (`/docs`)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import catalog
from app.derivation import derive
from app.generation import generate_backstory, generate_sheet, parse
from app.generation.client import ModelError
from app.generation.helpers import _ci, _norm

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
    roll_starting_wealth: bool = Field(
        default=False,
        description="If true, the character takes rolled starting gold INSTEAD of the class equipment "
                    "package (RAW): no class equipment is granted and the treasure is the rolled class "
                    "wealth plus background gold. Default false = keep equipment + background gold.")
    background: str | None = Field(
        default=None,
        description="Optional explicit background. If omitted, the service picks one (for variety).")
    fighting_style: str | None = Field(
        default=None,
        description="Optional explicit fighting style (only used by classes that get one). If omitted, "
                    "the service picks one for those classes.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"race": "<race>", "classes": [{"class": "<class>", "level": 5}]},
        {"race": "<race>",
         "classes": [{"class": "<class>", "level": 3}, {"class": "<class>", "level": 2}],
         "unique": "<optional flavour hint>"},
    ]})


class CharacterResponse(BaseModel):
    """The generated character: **choices** (what the model picked + code-injected fields) and the
    **sheet** (the derived numbers — abilities, modifiers, proficiency bonus, HP, AC, saves, skills,
    spell DC/attack, speed, hit dice)."""
    choices: dict
    sheet: dict


@router.post("/characters", response_model=CharacterResponse,
             summary="Generate a character (choices + derived sheet)",
             description=(
                 "Turn a request (race + class(es), optional per-class subclass overrides, optional "
                 "uniqueness hint) into a character's grammar-constrained, repaired **choices** "
                 "(name, background, alignment, abilities, skills, spells, feature/feat/equipment picks) "
                 "and the derived **sheet** computed from them (ability scores incl. ASIs, modifiers, "
                 "proficiency bonus, HP, AC, saving throws, skill table, spell save DC/attack, speed, "
                 "hit dice). Race / class / level / subclass are code-resolved. **400** = unknown "
                 "race/class or out-of-range level."))
def create_character(req: CharacterRequest) -> CharacterResponse:
    cat = catalog.get_catalog()
    try:
        spec = parse(cat, req.model_dump(by_alias=True))
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        choices = generate_sheet(cat, spec)
        sheet = derive(cat, choices)
    except ModelError as e:
        raise HTTPException(status_code=502, detail=f"model backend error: {e}")
    return CharacterResponse(choices=choices, sheet=sheet)


class BackstoryRequest(BaseModel):
    character: dict = Field(
        description="A character's choices (as returned by /v1/characters); needs at least "
                    "'race' and 'classes'. More fields (name, alignment, background, spells) "
                    "give the backstory more to work with.")
    unique: str | None = Field(
        default=None,
        description="Optional 'what is unique about this character?' hint. If omitted, a random "
                    "angle is used so backstories stay varied.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"character": {"race": "<race>", "classes": [{"class": "<class>", "level": 5}],
                       "name": "<name>", "background": "<background>"},
         "unique": "<optional flavour hint>"},
    ]})


class BackstoryResponse(BaseModel):
    """The flavour bundle: physical traits, personality (traits/ideal/bond/flaw), and a backstory."""
    flavour: dict


@router.post("/backstory", response_model=BackstoryResponse,
             summary="Generate a character's flavour (backstory bundle)",
             description=(
                 "Given a character's choices, generate physical traits (race-bounded), personality "
                 "(two traits + ideal/bond/flaw), and a short backstory — grounded in the sheet. "
                 "Physical bounds are clamped server-side. **400** if the character lacks race/classes."))
def create_backstory(req: BackstoryRequest) -> BackstoryResponse:
    cat = catalog.get_catalog()
    character = dict(req.character)
    race, classes = character.get("race"), character.get("classes")
    if not race or not classes:
        raise HTTPException(status_code=400, detail="character must include 'race' and 'classes'")
    # validate against the catalog (like /v1/characters) so garbage race/class never reaches the model
    if _norm(race) not in {_norm(r) for r in cat.get("valid_races", [])}:
        raise HTTPException(status_code=400, detail=f"unknown race: {race!r}")
    for c in classes:
        if not cat.record("classes", _ci(c.get("class", ""))):
            raise HTTPException(status_code=400, detail=f"unknown class: {c.get('class')!r}")
    if req.unique:
        character["unique"] = req.unique
    try:
        return BackstoryResponse(flavour=generate_backstory(cat, character))
    except ModelError as e:
        raise HTTPException(status_code=502, detail=f"model backend error: {e}")
