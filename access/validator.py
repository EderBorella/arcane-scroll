"""Feature-access file: VALIDATOR — BOILERPLATE.

One feature-access file per consuming app. This file will hold the queries the validator actually
needs, composed from the shared primitives (access.primitives) over a read-only RulesDB handle.

It is intentionally a scaffold. The validator itself is being (re)built as a separate task; the real
lookups get written here then, against the validator's true needs. Any business-rule math carried
over from the old validator is UNVERIFIED — re-derive it from the rulebook, do not trust it.

Rule of thumb: raw SQL lives in `primitives`; how-to-compose lives here; business rules
(proficiency-bonus math, spell-slot selection, totals) live here too, clearly and freshly derived.
"""
from access.db import RulesDB
from access import primitives as p


class ValidatorAccess:
    """Validator-facing view over the rulebook DB. Compose primitives into the exact lookups the
    validator needs; keep this thin over `primitives`."""

    def __init__(self, db: RulesDB | None = None, path: str | None = None):
        self.db = db or RulesDB(path)

    # -- worked example: the pattern every method below should follow -----------
    def grants_from_source(self, owner_kind: str, owner_id: str, at_level: int | None = None) -> dict:
        """Everything one source (species / class / subclass / feat / background / magic_item …)
        confers by a given level. A thin pass-through to the fan-out primitive — the shape most
        validator checks start from."""
        return p.all_grants_for(self.db, owner_kind, owner_id, at_level)

    # -- TODO (scoped when the validator is (re)built) --------------------------
    # Sketches only — signatures may change; business rules must be re-derived, not copied.
    #
    # def legal_skill_pool(self, classes, background): ...   # class_skill_option ∪ background_skill
    # def expected_spell_slots(self, classes): ...           # multiclass_slot / pact_slot + caster-level rule
    # def proficiency_bonus(self, level): ...                # business rule — derive from the rulebook
    # def feats_available(self, classes, has_background): ...
    # def features_expected(self, class_id, level): ...      # -> p.features_at(...)
    # def resource_value(self, resource_id, level): ...      # -> p.resource_at(...)
