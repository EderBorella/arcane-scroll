"""Model client — the layer's only impure module. No real network: urlopen is monkeypatched.
Focus is error mapping: backend/parse failures must become ModelError (→ 502 at the controller)."""
import io
import json
import urllib.error

import pytest

from app.generation import client


def _envelope(payload_text):
    return io.BytesIO(json.dumps({"response": payload_text}).encode())


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://model")
    monkeypatch.setenv("MODEL", "test-model")


def test_generate_parses_response(monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                        lambda *a, **k: _envelope(json.dumps({"name": "Ok"})))
    assert client.generate("prompt", {"type": "object"}) == {"name": "Ok"}


def test_network_error_becomes_modelerror(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    with pytest.raises(client.ModelError, match="unreachable"):
        client.generate("prompt", {})


def test_unparseable_model_output_becomes_modelerror(monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *a, **k: _envelope("not valid json{"))
    with pytest.raises(client.ModelError, match="invalid JSON"):
        client.generate("prompt", {})
