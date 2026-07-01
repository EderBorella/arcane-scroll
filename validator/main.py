"""HTTP entry for the validator micro-service. `POST /validate` takes a character sheet (the shared
CharacterSheet contract) and returns the full report — every finding at once. The 2024 rules are
loaded once at startup from the data dir (VALIDATOR_DATA)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from validator.rules import Rules
from validator.validate import validate as run_validate

_state = {}


@asynccontextmanager
async def lifespan(app):
    _state["rules"] = Rules.load(os.environ.get("VALIDATOR_DATA", "/rules"))
    yield
    _state.clear()


app = FastAPI(title="Arcane Scroll — character-sheet validator (2024)", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    r = _state.get("rules")
    return {"ready": r is not None,
            "rules": ({"classes": len(r.class_progression), "backgrounds": len(r.backgrounds),
                       "spells": len(r.all_spells())} if r else {})}


@app.post("/validate", summary="Validate a character sheet against the 2024 rules",
          description=("Body: a CharacterSheet (the shared contract). Returns "
                       "`{legal, complete, violations[], summary}` — every finding at once; a failing "
                       "check never stops the run."))
def validate_sheet(sheet: dict) -> dict:
    return run_validate(sheet, _state["rules"])
