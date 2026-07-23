"""The Orchestrator — the sole integrator in the Controller -> Orchestrator -> Services topology.

Controllers (thin HTTP adapters) call the Orchestrator; the Orchestrator is the only place that
composes the underlying single-responsibility services. It stays model-free: the model is reachable
only through the generator service, never from here. What it composes directly is the model-free rule
engine (``engine`` — the choice grammar + the derivation pipeline) and the validator service
functions (``validator`` — the per-sheet checks). Neither touches ``app`` or the model.

Two document flows land here (F07 D5/D6):

* ``derive`` (``/v1/derive``) — a stateless, deterministic, NO-model derive: parse a minimal build
  spec, assemble the caller's explicit choices, derive the five-schema document, and compose the
  completeness report.
* ``validate_document`` (``/validate-document``) — validate a supplied ``character-document`` envelope
  and return the one folded completeness report.

Both share :func:`orchestrator.report.compose_report`. A fresh read-only rules-DB access handle is
opened per call and closed on every path (mirroring the generator/validator services), so each call
owns its own connection.
"""
from access.generator import GeneratorAccess
from engine.choices import assemble, options, parse_request
from engine.derivation.document import derive_document
from orchestrator.report import compose_report
from orchestrator.services import ServiceRegistry

# The transport-envelope sheets, in document order (character-document:1). CORE is authoritative and
# always present; the rest are folded in only when the build produced them.
_ENVELOPE_SHEETS = ("core", "inventory", "grimoire", "modifier", "companion")


def _identity_defaults(payload: dict) -> dict:
    """Pass the contract-required identity metadata (``character_id`` / ``character_name``) straight
    through. The caller owns the character's identity — the derive is stateless and the sheet is
    user-editable, so there is nothing meaningful to invent here. When the caller omits a field it
    defaults to an empty string (a valid non-null placeholder the caller fills in); a supplied value
    is kept verbatim."""
    out = dict(payload)
    for key in ("character_id", "character_name"):
        if not out.get(key):
            out[key] = ""
    return out


def _envelope(document: dict) -> dict:
    """A ``character-document`` envelope from a derived document — the present sheets plus the light-v1
    ``schema_version``. Absent sheets (no GRIMOIRE / COMPANION) are simply omitted."""
    envelope: dict = {"schema_version": 1}
    for key in _ENVELOPE_SHEETS:
        if key in document:
            envelope[key] = document[key]
    return envelope


class Orchestrator:
    def __init__(self, services: ServiceRegistry | None = None, access_factory=None) -> None:
        # The downstream services this integrator composes. Empty in the skeleton; the document flows
        # compose the engine + validator as in-process libraries rather than remote clients.
        self.services = services or ServiceRegistry()
        # A zero-arg callable returning a FRESH read-only access handle. Default reads the rules DB
        # from $ARCANE_RULES_DB; a test injects one bound to the synthetic DB. Per-call (not per
        # process) so each request owns its own single-thread sqlite connection.
        self._access_factory = access_factory or GeneratorAccess

    def ready(self) -> dict:
        """Readiness for the orchestrator process. The skeleton is ready once constructed; as
        downstream service clients are registered, this folds in their reachability."""
        return {"ready": True, "services": self.services.names()}

    def derive(self, payload: dict) -> dict:
        """Stateless, deterministic derive from a minimal build spec (no model call).

        ``payload`` carries the build fundamentals — ``species`` / ``classes`` (each ``{class,
        level}``) / optional ``subclasses`` / ``background`` / ``alignment`` — plus an optional
        ``choices`` object of the caller's explicit picks (skills, feats, spells, languages, tools,
        expertise, the background ability-boost distribution, ...). A missing fundamental fails fast:
        :func:`parse_request` raises ``ValueError`` (mapped to HTTP 400 by the controller).

        Returns ``{"document": <character-document>, "report": <completeness-report>}``. Same input
        always yields the same output: the subclass is taken only from an explicit override (never
        randomly resolved) and no choice is invented — an unfilled choice is left empty for the report
        to flag."""
        access = self._access_factory()
        try:
            spec = parse_request(access, _identity_defaults(payload))
            # Deterministic: the subclass comes ONLY from an explicit override; if the level unlocks
            # one and none was supplied it stays None, and the manifest flags it. No random pick.
            resolved = [(cid, lv, spec.subclasses.get(cid)) for cid, lv in spec.classes]
            feat_slots = options.ability_feat_slot_count(access, resolved)
            boon_slots = options.boon_slot_count(access, resolved)
            picks = payload.get("choices") or {}
            choices = assemble.assemble_choices(access, spec, resolved, picks,
                                                feat_slots=feat_slots, boon_slots=boon_slots)
            document = derive_document(choices, access)
            envelope = _envelope(document)
            report = compose_report(envelope, access)
            return {"document": envelope, "report": report}
        finally:
            access.db.close()

    def validate_document(self, envelope: dict) -> dict:
        """Validate a supplied ``character-document`` envelope and return the one folded
        ``completeness-report`` (validator verdict + completeness manifest)."""
        access = self._access_factory()
        try:
            return compose_report(envelope, access)
        finally:
            access.db.close()
