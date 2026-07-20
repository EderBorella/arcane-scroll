"""The services seam — the single-responsibility services the Orchestrator composes.

Each concern is its own service: the validator and the deriver are pure rule-math services; the
generator is a separate, deferred service. The Orchestrator reaches each one through a client
registered here. The model / Ollama is deliberately NOT something the orchestrator may hold — it is
reachable only from the generator service, never from this seam.

The D2 skeleton ships an empty registry; the derive / validate-document deliverables (F07 D5/D6)
register their concrete service clients here without touching the controller layer.
"""


class ServiceRegistry:
    """A name -> service-client map the Orchestrator composes. Empty in the D2 skeleton.

    Deliberately model-free: only downstream single-responsibility services (validator, deriver,
    generator) belong here — never the model.
    """

    def __init__(self) -> None:
        self._services: dict[str, object] = {}

    def register(self, name: str, client: object) -> None:
        self._services[name] = client

    def get(self, name: str) -> object | None:
        return self._services.get(name)

    def names(self) -> list[str]:
        return sorted(self._services)
