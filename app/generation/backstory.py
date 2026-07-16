"""Backstory generator — physical traits (species-bounded), personality, and a short backstory, in
one structured model call grounded in a character's sheet.

Same shape as the sheet generator: a thin orchestrator over pure helpers (helpers.py); the model
picks, code bounds the result. When the request carries no 'unique' hint, a random seed angle
(archetype) is injected to keep backstories varied — otherwise the model leans on a default skeleton.
Numeric bounds can't be enforced by the grammar, so code clamps age/height/weight after. The flavour
data (physical bounds, appearance palettes, story angles, the prompt) is read from the reference DB
via the generator access layer — the request carries a species id, resolved through the DAL."""
import random

from access.generator import catalog as C
from access.generator import flavour as F
from app.generation import client
from app.generation import helpers as H


def build_schema(access, species_id):
    """OUTPUT contract: physical (species-bounded ints + enums), personality, and a backstory string."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = H.physical_bounds(access, species_id)
    props = {
        "age": {"type": "integer", "minimum": amin, "maximum": amax},
        "height_inches": {"type": "integer", "minimum": hmin, "maximum": hmax},
        "weight_lbs": {"type": "integer", "minimum": wmin, "maximum": wmax},
        "gender": {"enum": H.appearance_options(access, "gender", species_id)},
        "eyes": {"enum": H.appearance_options(access, "eyes", species_id)},
        "hair": {"enum": H.appearance_options(access, "hair", species_id)},
        "skin": {"enum": H.appearance_options(access, "skin", species_id)},
        "personality_traits": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "ideal": {"type": "string"},
        "bond": {"type": "string"},
        "flaw": {"type": "string"},
        "backstory": {"type": "string"},
    }
    return {"type": "object", "properties": props, "required": list(props)}


def build_prompt(access, character, species_id, species_name, *, unique=None, archetype=None):
    """ChatML: the flavour system prompt + the sheet summary + species bounds + (the unique hint or
    a seed angle)."""
    (amin, amax), (hmin, hmax), (wmin, wmax) = H.physical_bounds(access, species_id)
    user = (f"Character sheet:\n{H.character_summary(character, species_name)}\n"
            f"Physical limits for a {species_name}: age {amin}-{amax} yrs, height {hmin}-{hmax} in, "
            f"weight {wmin}-{wmax} lb.\nGenerate this character's full flavour.")
    if unique:
        user += f' The player notes what is unique about this character: "{unique}". Make it central.'
    elif archetype:
        user += f" Story angle to follow: {archetype}"
    return (f"<|im_start|>system\n{F.generator_prompt(access, 'flavour_sys')}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def generate(access, character, *, rng=random):
    """Orchestrator: resolve the species id -> display name → pick the steer (the request's 'unique'
    hint, else a random archetype) → build schema + prompt → model → clamp physical bounds → flavour
    bundle."""
    species_id = character.get("species", "")
    species_name = C.name_of(access, "species", species_id) or species_id
    unique = character.get("unique")
    archetypes = F.story_archetypes(access)
    archetype = None if unique or not archetypes else rng.choice(archetypes)
    schema = build_schema(access, species_id)
    text = build_prompt(access, character, species_id, species_name, unique=unique, archetype=archetype)
    flavour = client.generate(text, schema, num_ctx=4096, num_predict=1024, temperature=0.8)
    return H.clamp_physical(access, species_id, flavour)
