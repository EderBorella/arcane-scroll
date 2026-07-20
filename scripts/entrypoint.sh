#!/bin/sh
# Generator container entrypoint: ensure the model is present, then serve. Idempotent, so a fresh
# host needs no manual setup. Only the generator uses this entrypoint (it is the sole model
# consumer); the validator and orchestrator override it and never run the model-pull step.
set -e

python /app/scripts/provision.py     # wait for Ollama + idempotent model pull

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
