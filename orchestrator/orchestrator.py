"""The Orchestrator — the sole integrator in the Controller -> Orchestrator -> Services topology.

Controllers (thin HTTP adapters) call the Orchestrator; the Orchestrator is the only place that
composes the underlying single-responsibility services (validator, deriver, and — separately — the
generator). It never depends on the model: the model is reachable only through the generator
service, never from here.

This is the D2 skeleton: it stands up the seam and a readiness signal. The derive / validate-document
flows (F07 D5/D6) register their service clients on the registry and add their methods here, without
the controller layer having to change.
"""
from orchestrator.services import ServiceRegistry


class Orchestrator:
    def __init__(self, services: ServiceRegistry | None = None) -> None:
        # The downstream services this integrator composes. Empty in the skeleton; the
        # derive / validate deliverables register their service clients here.
        self.services = services or ServiceRegistry()

    def ready(self) -> dict:
        """Readiness for the orchestrator process. The skeleton is ready once constructed; as
        downstream service clients are registered, this folds in their reachability."""
        return {"ready": True, "services": self.services.names()}
