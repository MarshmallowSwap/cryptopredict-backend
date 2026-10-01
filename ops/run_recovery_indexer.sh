#!/usr/bin/env bash
set -euo pipefail
ROOT=/opt/cryptopredict-recovery
ENV_FILE=/etc/cryptopredict-recovery.env
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE"; exit 1; }
cd "$ROOT/current"
set -a
source "$ENV_FILE"
set +a
exec "$ROOT/venv/bin/python" scripts/recovery_indexer.py
