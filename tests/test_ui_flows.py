"""
The UI rehearsals, run as part of the normal suite.

The rehearsal itself lives in ``scripts/verify_ui_flows.py`` so an instructor can
run it standalone, but it must also fail the build when it breaks -- otherwise
the professor flow can rot between demos without anybody noticing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run(rehearsal_name: str):
    import importlib

    module = importlib.import_module("scripts.verify_ui_flows")
    module.CHECKS.clear()
    getattr(module, rehearsal_name)()
    failures = [c for c in module.CHECKS if not c[1]]
    assert module.CHECKS, f"{rehearsal_name} produced no checks"
    assert not failures, "\n".join(f"{step}: {detail}" for step, _, detail in failures)
    return module.CHECKS


def test_professor_can_play_the_whole_game_on_screen():
    checks = _run("rehearsal_professor")
    names = [c[0] for c in checks]
    assert "professor can reach the debrief without a terminal" in names
    assert "all four rounds appear in the agenda" in names


def test_student_screen_shows_only_its_own_model():
    checks = _run("rehearsal_student")
    names = [c[0] for c in checks]
    assert "what does our model say?" in names
    assert "no other fund's private model leaks onto our screen" in names


def test_debrief_answers_all_ten_questions():
    checks = _run("rehearsal_debrief")
    answered = [c for c in checks if c[0] == "all ten questions are answered on screen"]
    assert answered and answered[0][1], answered[0][2] if answered else "no check"
