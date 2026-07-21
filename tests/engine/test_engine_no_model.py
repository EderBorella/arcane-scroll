"""The model-free rule engine must carry NO model dependency (F07 rule-engine extraction).

The engine (``engine.choices`` + ``engine.derivation``) is the standalone package the orchestrator
service composes for /v1/derive without reaching the model. It reads only the data-access layer
(``access/*``). It must never import the generator service (``app`` — where the model client lives),
the model server client / provisioner (``ollama`` / ``scripts.provision``), the validator checks
(``validator``), or the orchestrator. This mirrors the orchestrator's own no-model guard, scanning
the import graph over the engine tree rather than trusting prose.
"""
import ast
import pathlib

# The access layer package the engine legitimately reads (``access.validator`` is the ACCESS layer,
# not the ``validator`` checks package — the forbidden-prefix match below excludes it because it
# starts with ``access.``, never ``validator``).


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_engine_carries_no_model_dependency():
    root = pathlib.Path(__file__).parents[2] / "engine"
    # The generator service (`app`, which houses the model client), the model server client and its
    # provisioner, the validator checks, and the orchestrator are all off-limits to the engine.
    forbidden = ("app", "ollama", "scripts.provision", "validator", "orchestrator")
    for p in root.rglob("*.py"):
        for mod in _imported_modules(p):
            assert not any(mod == f or mod.startswith(f + ".") for f in forbidden), (
                f"{p} imports {mod}")
