#!/bin/sh
# App container entrypoint: ensure the model, (re)build the in-memory store's DB from the mounted
# data, then serve. Each step is idempotent, so a fresh host needs no manual setup.
set -e

python /app/scripts/provision.py     # wait for Ollama + idempotent model pull
python /app/scripts/seed.py          # (re)build the catalog DB from the mounted reference data

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
