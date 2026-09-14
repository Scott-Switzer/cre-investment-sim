"""
Regenerate the engine service's golden contract fixtures.

    uv run python scripts/export_engine_fixtures.py

Every expected response in `tests/contracts/engine_api/` is emitted here by the
verified Python engine. Nothing is typed by hand, because a hand-written
expectation is a second implementation of the rules -- which is precisely the
duplication the engine-as-a-service approach exists to avoid.

Run this whenever the engine's contract legitimately changes, then review the diff:
a fixture that changed without a matching intent is the failure this catches.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from service.engine_api import fixtures  # noqa: E402


def main() -> None:
    print("Regenerating engine contract fixtures from the live engine…")
    count = fixtures.write_fixtures(verbose=True)
    print(f"\n{count} fixtures written to {fixtures.CONTRACT_DIR.relative_to(REPO_ROOT)}")
    states = sorted((fixtures.CONTRACT_DIR / fixtures.STATE_DIRNAME).glob("*.json.gz"))
    total = sum(path.stat().st_size for path in states)
    print(f"{len(states)} engine states, {total / 1024:.0f} KB gzipped")


if __name__ == "__main__":
    main()
