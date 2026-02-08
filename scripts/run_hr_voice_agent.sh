#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Single root venv
source venv/bin/activate

python -m pip install -r services/hr_voice_agent/requirements.txt >/dev/null

exec python -m uvicorn --app-dir services/hr_voice_agent hr_voice_agent.app:app \
  --host 0.0.0.0 --port 8081 --reload
