#!/usr/bin/env python3
"""One-pass verification: lint + tests + demo flow + NAV identity + build."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/tmp/cre-investment-sim")
PYTHON = str(REPO / ".venv" / "bin" / "python")

def run(cmd: list[str], label: str, timeout: int = 120) -> int:
    print(f"\n# {label}")
    print(f"#   {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"FAIL  {label}: timed out after {timeout}s")
        return 124
    code = r.returncode
    out = r.stdout
    if code == 0:
        # keep last 5 lines only when passing
        lines = out.strip().splitlines()
        print("\n".join(lines[-5:]) if lines else "(no output)")
        print(f"PASS  {label} (exit 0)")
        return 0
    # on failure print head + tail so the cause is visible
    lines = out.splitlines()
    head = lines[:12] if len(lines) > 12 else lines
    tail = lines[-12:] if len(lines) > 12 else []
    print("stdout:")
    print("\n".join(head))
    if tail and tail != head:
        print("...")
        print("\n".join(tail))
    if r.stderr:
        print("stderr:", r.stderr[:2000])
    print(f"FAIL  {label} (exit {code})")
    return code

def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    r = 0
    r |= run([PYTHON, "-m", "ruff", "check", "."], "ruff (lint)")
    r |= run([PYTHON, "-m", "mypy", "."], "mypy (types)", timeout=120)
    # pytest is slow to import; cap at 4 minutes
    r |= run([PYTHON, "-m", "pytest", "tests/", "-q", "--tb=short"], "pytest", timeout=240)
    r |= run([PYTHON, "scripts/verify_demo_flow.py"], "demo flow (practice -> 4 rounds -> winner -> debrief)")
    r |= run([PYTHON, "scripts/verify_nav_identity.py"], "NAV identity")
    r |= run(
        ["pip-audit", "--quiet", "--cache-dir", str(repo / ".cache" / "pip-audit")],
        "known-vulnerable dependencies",
        timeout=120,
    )
    print("\n" + "=" * 78)
    if r == 0:
        print("ALL GREEN")
    else:
        print(f"EXIT {r}  (0=ok)")
    return r

if __name__ == "__main__":
    raise SystemExit(main())
