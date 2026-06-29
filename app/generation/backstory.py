"""Backstory generator — physical traits (race-bounded), personality, and a short backstory, in one
structured model call grounded in a character's sheet.

Same shape as the sheet generator: a thin orchestrator over pure helpers (helpers.py); the model
picks, code bounds the result. When the request carries no 'unique' hint, a random seed angle
(archetype) is injected to keep backstories varied — otherwise the model leans on a default skeleton.
Numeric bounds can't be enforced by the grammar, so code clamps age/height/weight after."""
import random

from app.generation import client
from app.generation import helpers as H


def build_schema(cat, race):
    """OUTPUT contract: physical (race-bounded ints + enums), personality, and a backstory string."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = H.physical_bounds(cat, race)
    props = {
        "age": {"type": "integer", "minimum": amin, "maximum": amax},
        "height_inches": {"type": "integer", "minimum": hmin, "maximum": hmax},
        "weight_lbs": {"type": "integer", "minimum": wmin, "maximum": wmax},
        "gender": {"enum": cat.get("genders")},
        "eyes": {"enum": cat.get("eyes")},
        "hair": {"enum": cat.get("hair")},
        "skin": {"enum": H.skin_options(cat, race)},
        "personality_traits": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "ideal": {"type": "string"},
        "bond": {"type": "string"},
        "flaw": {"type": "string"},
        "backstory": {"type": "string"},
    }
    return {"type": "object", "properties": props, "required": list(props)}


def build_prompt(cat, character, *, unique=None, archetype=None):
    """ChatML: the flavour system prompt + the sheet summary + race bounds + (the unique hint or
    a seed angle)."""
    race = character.get("race", "")
    (amin, amax), (hmin, hmax), (wmin, wmax) = H.physical_bounds(cat, race)
    user = (f"Character sheet:\n{H.character_summary(character)}\n"
            f"Physical limits for a {race}: age {amin}-{amax} yrs, height {hmin}-{hmax} in, "
            f"weight {wmin}-{wmax} lb.\nGenerate this character's full flavour.")
    if unique:
        user += f' The player notes what is unique about this character: "{unique}". Make it central.'
    elif archetype:
        user += f" Story angle to follow: {archetype}"
    return (f"<|im_start|>system\n{cat.prompt('flavour_sys')}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def generate(cat, character, *, rng=random):
    """Orchestrator: pick the steer (the request's 'unique' hint, else a random archetype) → build
    schema + prompt → model → clamp physical bounds → flavour bundle."""
    unique = character.get("unique")
    archetypes = cat.get("archetypes") or []
    archetype = None if unique or not archetypes else rng.choice(archetypes)
    schema = build_schema(cat, character.get("race", ""))
    text = build_prompt(cat, character, unique=unique, archetype=archetype)
    flavour = client.generate(text, schema, num_ctx=4096, num_predict=1024, temperature=0.8)
    return H.clamp_physical(cat, character.get("race", ""), flavour)
