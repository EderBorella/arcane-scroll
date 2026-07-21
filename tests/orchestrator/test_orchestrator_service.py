"""Orchestrator service skeleton (F07 D2): the health/readiness routes and the
Controller -> Orchestrator -> Services seam. The orchestrator must carry NO model dependency."""
import ast
import pathlib

from fastapi.testclient import TestClient

from orchestrator.main import app
from orchestrator.orchestrator import Orchestrator
from orchestrator.services import ServiceRegistry


def test_health():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_ready_skeleton():
    with TestClient(app) as c:
        body = c.get("/ready").json()
        assert body["ready"] is True
        assert body["services"] == []          # no downstream services registered yet


def test_orchestrator_composes_registered_services():
    reg = ServiceRegistry()
    reg.register("validator", object())
    orch = Orchestrator(reg)
    assert orch.ready() == {"ready": True, "services": ["validator"]}


def test_service_registry_get():
    reg = ServiceRegistry()
    sentinel = object()
    reg.register("deriver", sentinel)
    assert reg.get("deriver") is sentinel
    assert reg.get("absent") is None


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_orchestrator_carries_no_model_dependency():
    # The model is reachable ONLY from the generator service; the orchestrator seam must never IMPORT
    # the generator internals or the model server client (checked on the import graph, not prose).
    # Forbid the whole `app` package — importing any of it transitively pulls in the generation/model
    # path (the model client `app.generation.client` lives there) — plus the model server client and
    # its provisioner. The model-free rule engine (`engine`) is deliberately NOT forbidden: it is the
    # standalone package the orchestrator composes for /v1/derive (D5) without touching app/the model.
    root = pathlib.Path(__file__).parents[2] / "orchestrator"
    forbidden = ("app", "ollama", "scripts.provision")
    for p in root.rglob("*.py"):
        for mod in _imported_modules(p):
            assert not any(mod == f or mod.startswith(f + ".") for f in forbidden), f"{p} imports {mod}"
