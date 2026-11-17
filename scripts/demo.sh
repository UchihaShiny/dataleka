#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo 'Cần cài môi trường .venv theo docs/analytics-app.md' >&2
  exit 1
fi
# Never load .env or instantiate a cloud/Claude client in this explicit mode.
export DATAE_MODE=demo PYTHON_DOTENV_DISABLED=1
exec .venv/bin/python -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8600 "$@"
