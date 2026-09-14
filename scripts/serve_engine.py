"""
Local entrypoint for the engine service.

    uv run python scripts/serve_engine.py            # 127.0.0.1:8080
    PORT=9090 uv run python scripts/serve_engine.py

Cloud Run sets ``PORT`` and expects the process to bind it on all interfaces, so
``HOST`` defaults to ``0.0.0.0`` there and to loopback locally. There is no secret
here and no config file: the service is stateless, and everything it needs is in the
request body or on disk under ``config/bundles/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    uvicorn.run(
        "service.engine_api.app:app",
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
