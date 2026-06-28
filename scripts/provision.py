#!/usr/bin/env python3
"""Wait for Ollama to be reachable, then idempotently ensure the configured model is present
(a pull is a no-op when the model already exists). Data-free; paths/names from the environment:
  OLLAMA_URL   base URL of the Ollama service
  MODEL        model tag to ensure
"""
import json
import os
import sys
import time
import urllib.request


def _req(url, data=None, timeout=600):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    return urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=timeout)


def main():
    base = os.environ.get("OLLAMA_URL")
    model = os.environ.get("MODEL")
    if not base or not model:
        sys.exit("ERROR: set OLLAMA_URL and MODEL")

    print(f"[provision] waiting for Ollama at {base} ...", flush=True)
    for _ in range(150):  # ~5 min
        try:
            _req(f"{base}/api/tags", timeout=5)
            break
        except Exception:
            time.sleep(2)
    else:
        sys.exit("[provision] Ollama did not become ready in time")

    print(f"[provision] ensuring model '{model}' (idempotent pull) ...", flush=True)
    _req(f"{base}/api/pull", {"name": model, "stream": False})
    print("[provision] model ready", flush=True)


if __name__ == "__main__":
    main()
