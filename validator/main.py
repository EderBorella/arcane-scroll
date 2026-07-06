"""Validation micro-service. Builds one read-only ValidatorAccess at startup (from $ARCANE_RULES_DB)
and validates posted character sheets against it."""
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI

from access.validator import ValidatorAccess
from validator.validate import validate

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
