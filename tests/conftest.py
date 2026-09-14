"""
Put the repository root on `sys.path`.

The suite is normally run as `python -m pytest`, which happens to insert the
working directory for you. Adding it explicitly means `pytest tests/` from any
directory resolves `src.*` and `service.*` the same way, rather than depending on
how the command was typed.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
