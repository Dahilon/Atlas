#!/usr/bin/env bash
# Run the FastAPI backend. Use from project root: ./run-backend.sh

set -e
cd "$(dirname "$0")"

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

PYTHONPATH=backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
