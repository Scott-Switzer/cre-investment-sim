#!/usr/bin/env python3
"""
Rehearse the real Streamlit screens, in-process, with no terminal steps.

A browser click-through is not reproducible and cannot be re-run in CI, so the
rehearsal is driven through Streamlit's own ``AppTest`` harness. It exercises the
same page modules the user sees, clicks the same buttons, and reads the rendered
elements.

Three rehearsals:

    PROFESSOR   start a demo game, then drive practice + four rounds to the
                debrief using only on-screen controls
    STUDENT     confirm the live screen shows the round, the cash, the deals, and
                that team's OWN model — and no other team's
    DEBRIEF     confirm the final screen answers the ten questions

Run:

    uv run python scripts/verify_ui_flows.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from streamlit.testing.v1 import AppTest  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(step: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append((step, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {step}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def rendered(at: AppTest) -> str:
    """All visible text on the page, lowercased for tolerant matching."""
    chunks: list[str] = []
    for kind in (
        "title", "header", "subheader", "markdown", "caption", "text",
        "info", "success", "warning", "error",
    ):
        for el in getattr(at, kind, []) or []:
            value = getattr(el, "value", None)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
    return "\n".join(chunks)


def ss_get(at: AppTest, key: str, default=None):
    """AppTest's session state has no ``.get``; index it defensively."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def button_labels(at: AppTest) -> list[str]:
    out = []
    for b in at.button:
        label = getattr(b, "label", "") or ""
        if isinstance(label, str):
            out.append(label)
    return out


def click(at: AppTest, label: str) -> bool:
    """Click the first button with this exact label and re-run the page."""
    for b in at.button:
        if (getattr(b, "label", "") or "") == label:
            b.click().run()
            return True
    return False


# ── PROFESSOR REHEARSAL ──────────────────────────────────────────────────

def rehearsal_professor() -> None:
    print("\nPROFESSOR FLOW — professor_control.py, on-screen controls only")
    at = AppTest.from_file(str(REPO / "pages" / "professor_control.py"))
    at.run()
    check("professor page loads", not at.exception, str(at.exception[:1]))

    labels = button_labels(at)
    check("TRY DEMO is offered", "TRY DEMO" in labels, f"buttons={labels}")

    check("TRY DEMO starts a game", click(at, "TRY DEMO"))
    gm = ss_get(at, "game_manager")
    check("a game exists after TRY DEMO", gm is not None)
    if gm is None:
        return

    check("four funds are competing", len(gm.teams) == 4,
          f"{sorted(gm.teams)}")
    human = gm.teams.get("Buy&Hold Capital")
    check("the human seat has a preloaded model",
          human is not None and len(human.model_predictions) > 0,
          f"{len(human.model_predictions) if human else 0} predictions")
    check("game starts in the practice round", gm.current_round == -1,
          f"round={gm.current_round}")
    check("progress strip starts at PRACTICE", "PRACTICE" in rendered(at))

    # Drive the whole game with the on-screen auto-advance control only.
    stage_sequence: list[str] = []
    for step in range(40):
        if gm.game_complete:
            break
        if not click(at, "Auto-Advance Next Round"):
            # Fall back to the resolve control if auto-advance is unavailable.
            if not click(at, "Resolve Round"):
                check(f"round control available at step {step}", False,
                      f"buttons={button_labels(at)}")
                break
        gm = ss_get(at, "game_manager")
        if gm is None:
            check("game manager survived a transition", False)
            break
        from src.game.manager import game_stage
        stage = game_stage(gm)
        if not stage_sequence or stage_sequence[-1] != stage:
            stage_sequence.append(stage)
        if at.exception:
            check(f"no exception during {stage}", False, str(at.exception[:1]))
            break

    gm = ss_get(at, "game_manager")
    check("professor can reach the debrief without a terminal",
          gm is not None and gm.game_complete)
    check("every round was played", len(gm.round_history) == 4,
          f"{sorted(gm.round_history)}")
    check("stage sequence walked the agenda",
          stage_sequence[:2] == ["PRACTICE", "ROUND 1"] and
          stage_sequence[-1] == "DEBRIEF",
          " -> ".join(stage_sequence))
    check("all four rounds appear in the agenda",
          all(f"ROUND {i}" in stage_sequence for i in (1, 2, 3, 4)),
          " -> ".join(stage_sequence))
    check("no exceptions during the whole game", not at.exception,
          str(at.exception[:1]))

    # The event log should have recorded the operator's actions.
    check("round control actions were logged", len(gm.event_log) > 0,
          f"{len(gm.event_log)} entries")


# ── STUDENT REHEARSAL ────────────────────────────────────────────────────

def rehearsal_student() -> None:
    print("\nSTUDENT FLOW — live_game.py, what must be obvious without instructions")
    from src.game.demo_setup import HUMAN_TEAM_ID, build_demo_game

    gm = build_demo_game()
    gm.start_game()

    at = AppTest.from_file(str(REPO / "pages" / "live_game.py"))
    at.session_state["game_manager"] = gm
    at.session_state["current_team"] = HUMAN_TEAM_ID
    at.run()
    check("live screen loads during practice", not at.exception, str(at.exception[:1]))

    text = rendered(at)
    check("what round is it?", "practice" in text.lower())
    cash_label = [m.label for m in at.metric]
    check("how much cash do we have?", "Cash" in cash_label, f"metrics={cash_label}")
    check("what is our NAV?", "NAV" in cash_label)
    check("what properties are available?", "market" in text.lower())
    check("what does our model say?", "your model" in text.lower())

    # The private model panel must show THIS team's numbers.
    team = gm.teams[HUMAN_TEAM_ID]
    pid = next(iter(gm.current_properties))
    own = team.model_predictions[pid]
    check("our model's fair value is displayed",
          f"{own.predicted_fair_value:.1f}" in text,
          f"expected {own.predicted_fair_value:.1f}")
    check("our model's max bid is displayed",
          f"{own.max_bid:.1f}" in text, f"expected {own.max_bid:.1f}")

    # Privacy: no other fund's numbers may appear on our screen.
    others = [t for tid, t in gm.teams.items() if tid != HUMAN_TEAM_ID]
    leaked = []
    for other in others:
        pred = other.model_predictions.get(pid)
        if pred is None:
            continue
        if f"{pred.max_bid:.1f}" == f"{own.max_bid:.1f}":
            continue
        if f"{pred.predicted_fair_value:.1f}" in text:
            leaked.append(other.team_name)
    check("no other fund's private model leaks onto our screen", not leaked,
          f"leaked={leaked}")

    # Bidding must be possible and must show the equity required.
    at2 = AppTest.from_file(str(REPO / "pages" / "live_game.py"))
    at2.session_state["game_manager"] = gm
    at2.session_state["current_team"] = HUMAN_TEAM_ID
    at2.run()
    radios = [r for r in at2.radio]
    check("a PASS / BID choice is offered", len(radios) > 0,
          f"{len(radios)} decision controls")
    if radios:
        radios[0].set_value("BID").run()
        text2 = rendered(at2)
        check("choosing BID reveals price and leverage inputs",
              len(at2.number_input) > 0, f"{len(at2.number_input)} numeric inputs")
        check("equity required is shown before committing",
              "equity" in text2.lower())
    check("making a decision raises no exception", not at2.exception,
          str(at2.exception[:1]))


# ── DEBRIEF REHEARSAL ────────────────────────────────────────────────────

def rehearsal_debrief() -> None:
    print("\nDEBRIEF FLOW — final_debrief.py answers the ten questions")
    from src.game.bots import submit_bot_bids
    from src.game.demo_setup import HUMAN_TEAM_ID, build_demo_game

    gm = build_demo_game()
    gm.start_game()
    gm.lock_round()
    gm.resolve_round()
    gm.advance_round()
    for _ in range(gm.config.total_rounds):
        preds = gm.teams[HUMAN_TEAM_ID].model_predictions
        best, target = None, None
        for prop_id, prop in gm.current_properties.items():
            pred = preds.get(prop_id)
            if pred is None:
                continue
            edge = pred.predicted_fair_value - prop.asking_price
            if best is None or edge > best:
                best, target = edge, prop_id
        if target is not None:
            from src.game.adjudicator import Bid

            pred = preds[target]
            price = max(pred.max_bid * 0.99, gm.current_properties[target].reserve_price * 1.02)
            ltv = min(pred.target_ltv, gm.current_properties[target].max_ltv)
            try:
                gm.submit_bid(Bid(HUMAN_TEAM_ID, target, price, ltv,
                                  gm.current_round, "rehearsal"))
            except (ValueError, RuntimeError):
                pass
        submit_bot_bids(gm, HUMAN_TEAM_ID)
        gm.lock_round()
        gm.resolve_round()
        gm.advance_round()

    at = AppTest.from_file(str(REPO / "pages" / "final_debrief.py"))
    at.session_state["game_manager"] = gm
    at.run()
    check("debrief page loads", not at.exception, str(at.exception[:1]))

    text = rendered(at).lower()
    questions = [
        "who won the game",
        "who had the best model",
        "same team",
        "overrode their own model",
        "help or hurt",
        "most leverage",
        "create or destroy value",
        "looked right beforehand",
        "got lucky",
        "what should a student conclude",
    ]
    missing = [q for q in questions if q not in text]
    check("all ten questions are answered on screen", not missing,
          f"missing={missing}")

    for topic in ("where the money came from", "analytics leaderboard",
                  "model vs manager vs luck", "recorded overrides"):
        check(f"section present: {topic}", topic in text)

    check("the NAV channel decomposition is shown",
          "interest paid" in text and "noi income" in text)
    check("no exceptions rendering the debrief", not at.exception,
          str(at.exception[:1]))


def main() -> int:
    print("=" * 74)
    print("REAL 605 — UI FLOW REHEARSAL (Streamlit AppTest, no terminal steps)")
    print("=" * 74)
    rehearsal_professor()
    rehearsal_student()
    rehearsal_debrief()

    failures = [c for c in CHECKS if not c[1]]
    print("\n" + "=" * 74)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    if failures:
        print("FAILURES:")
        for step, _, detail in failures:
            print(f"  - {step} {detail}")
        print("UI FLOWS = FAIL")
        return 1
    print("UI FLOWS = PASS")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
