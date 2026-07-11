"""Validation micro-service. Builds one read-only ValidatorAccess at startup (from $ARCANE_RULES_DB)
and validates posted character sheets against it."""
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI

from access.validator import ValidatorAccess
from validator.validate import validate
from validator.validate_core import validate_core
from validator.validate_grimoire import validate_grimoire
from validator.validate_inventory import validate_inventory
from validator.validate_modifier import validate_modifier

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["access"] = ValidatorAccess(path=os.environ.get("ARCANE_RULES_DB"))
    yield
    _state.clear()


app = FastAPI(title="character-sheet validator", lifespan=lifespan)


@app.post("/validate")
async def validate_sheet(sheet: dict = Body(...)) -> dict:
    # async, not sync: keeps this on the same event-loop thread as `lifespan`, which is where the
    # RulesDB connection was opened — sqlite3 connections are single-thread-only, and a sync def here
    # would run in Starlette's worker threadpool and raise a cross-thread ProgrammingError.
    return validate(sheet, _state["access"])


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
