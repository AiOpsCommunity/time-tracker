#!/usr/bin/env bash
# Starts the local JSON-backed time tracker (time_tracker_json.html).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PORT="${1:-8934}"

exec python3 scripts/json_server.py --port "$PORT"
