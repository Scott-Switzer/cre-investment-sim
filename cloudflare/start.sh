#!/bin/sh
set -eu

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]; then
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/cre-google-credentials.json
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/cre-google-credentials.json
fi

PORT=8081 HOST=127.0.0.1 python scripts/serve_engine.py &
engine_pid=$!
trap 'kill "$engine_pid" 2>/dev/null || true' TERM INT EXIT

cd /app/services/game
exec node dist/index.js
