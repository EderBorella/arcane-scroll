"""Validation micro-service. Builds one read-only ValidatorAccess at startup (from $ARCANE_RULES_DB)
and validates posted character sheets against it."""
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI

from access.validator import ValidatorAccess
from validator.validate_companion import validate_companion
from validator.validate_core import validate_core
from validator.validate_grimoire import validate_grimoire
from validator.validate_inventory import validate_inventory
from validator.validate_modifier import validate_modifier
from validator.validate_monster import validate_monster

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["access"] = ValidatorAccess(path=os.environ.get("ARCANE_RULES_DB"))
    yield
    _state.clear()


app = FastAPI(title="character-sheet validator", lifespan=lifespan)


@app.post("/validate-core")
async def validate_core_sheet(sheet: dict = Body(...)) -> dict:
    return validate_core(sheet, _state["access"])


@app.post("/validate-grimoire")
async def validate_grimoire_sheet(body: dict = Body(...)) -> dict:
    return validate_grimoire(body["core"], body["grimoire"], _state["access"])


@app.post("/validate-inventory")
async def validate_inventory_sheet(body: dict = Body(...)) -> dict:
    return validate_inventory(body["core"], body["inventory"],
                              body.get("modifier"), _state["access"])


@app.post("/validate-modifier")
async def validate_modifier_sheet(body: dict = Body(...)) -> dict:
    return validate_modifier(body["core"], body["inventory"],
                              body["grimoire"], body["modifier"],
                              _state["access"])


@app.post("/validate-companion")
async def validate_companion_sheet(body: dict = Body(...)) -> dict:
    # {core, grimoire, companion}. GRIMOIRE supplies the owner spell attack/save
    # context needed to re-derive a templated companion's scaled values; concrete
    # creatures ignore it.
    return validate_companion(body["core"], body.get("grimoire"),
                              body["companion"], _state["access"])


@app.post("/validate-monster")
async def validate_monster_sheet(sheet: dict = Body(...)) -> dict:
    # A standalone monster-sheet:1 document (owner-less): {schema_version, monsters[]}.
    # No CORE, no owner GRIMOIRE — each concrete creature is re-derived from the
    # catalog; templated (owner-scaled) creatures are rejected.
    return validate_monster(sheet, _state["access"])
