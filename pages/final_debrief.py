"""
Final Debrief — the screen the professor teaches from.

Everything on this page is computed from recorded game history by
:mod:`src.game.analytics`. No language model adjudicates anything, and no
conclusion is asserted that the data does not support.

The page is organised around the ten questions the course wants to be able to
answer out loud:

    1 who won            6 who used the most leverage
    2 best model         7 did leverage create or destroy value
    3 same team?         8 which good decision had a bad outcome
    4 who overrode most  9 which team got lucky
    5 did overrides help 10 what should a student conclude

It also separates the three things students habitually conflate: the quality of
the model, the quality of the decision made with it, and luck.
"""

import streamlit as st
import pandas as pd

from src.game.analytics import (
    assess_attempts,
    debrief_answers,
)

DEBRIEF_CSS = """
<style>
.stApp {
    background-color: #f7fafc;
    color: #2d3748;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.page-header h1 {
    color: #1a365d;
    font-size: 2rem;
    font-weight: 600;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 0.5rem;
    margin-bottom: 0.5rem;
}
.page-header p {
    color: #718096;
    font-size: 1rem;
}
.section-header {
    font-size: 1.25rem;
    font-weight: 600;
    color: #2d3748;
    margin-top: 2rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid #e2e8f0;
}
.data-row {
    display: flex;
    justify-content: space-between;
    padding: 0.35rem 0;
    border-bottom: 1px solid #edf2f7;
}
.data-label {
    color: #718096;
    font-size: 0.9rem;
}
.data-value {
    font-weight: 600;
    color: #2d3748;
    font-size: 0.9rem;
}
.data-value.positive { color: #276749; }
.data-value.negative { color: #9b2c2c; }
.debrief-section {
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 1rem;
    margin-bottom: 1rem;
}
.interpretation {
    font-style: italic;
    color: #4a5568;
    padding: 0.5rem;
    border-left: 3px solid #e2e8f0;
    margin-bottom: 0.75rem;
}
.qa-card {
    border: 1px solid #e2e8f0;
    border-left: 4px solid #1a365d;
    border-radius: 4px;
    padding: 0.75rem 0.9rem;
    margin-bottom: 0.6rem;
    background: #ffffff;
}
.qa-card .q {
    font-weight: 700;
    color: #1a365d;
    font-size: 0.95rem;
    margin-bottom: 0.25rem;
}
.qa-card .a {
    color: #2d3748;
    font-size: 0.95rem;
    margin-bottom: 0.15rem;
}
.qa-card .d {
    color: #718096;
    font-size: 0.82rem;
}
.qa-card.teach-1 { border-left-color: #276749; }
.qa-card.teach-2 { border-left-color: #b7791f; }
.qa-card.teach-3 { border-left-color: #9b2c2c; }
.case-row {
    display: flex;
    justify-content: space-between;
    padding: 0.3rem 0;
    border-bottom: 1px solid #edf2f7;
    font-size: 0.88rem;
}
.case-row.present .count { color: #276749; font-weight: 700; }
.case-row.absent .count { color: #a0aec0; }
.model-matrix {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin: 1rem 0;
}
.matrix-cell {
    padding: 0.75rem;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
}
.matrix-cell.correct-followed { background: #f0fff4; border-color: #9ae6b4; }
.matrix-cell.correct-overridden { background: #fffff0; border-color: #f6e05e; }
.matrix-cell.wrong-followed { background: #fff5f5; border-color: #feb2b2; }
.matrix-cell.wrong-override-success { background: #ebf8ff; border-color: #90cdf4; }
.matrix-cell h5 { margin: 0 0 0.25rem 0; font-size: 0.85rem; font-weight: 600; }
.strategy-row {
    display: flex;
    align-items: center;
    padding: 0.25rem 0;
    border-bottom: 1px solid #edf2f7;
}
.strategy-round { font-weight: 600; color: #1a365d; min-width: 60px; }
.strategy-change { color: #4a5568; }
</style>
"""

NAMED_CASES = [
    ("MODEL GOOD + FOLLOWED MODEL", "Model right, model followed"),
    ("MODEL GOOD + BAD OVERRIDE", "Model right, human overrode it badly"),
    ("MODEL WRONG + GOOD OVERRIDE", "Model wrong, human judgment saved it"),
    ("GOOD DECISION + BAD REALIZED OUTCOME", "Right process, unlucky year"),
    ("BAD DECISION + LUCKY REALIZED OUTCOME", "Wrong process, paid anyway"),
]


# ── HELPERS ──────────────────────────────────────────────────────────────

def fmt_currency(val, precision=2):
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:,.{precision}f}M"


def fmt_pct(val):
    return f"{val:.1%}"


def fmt_delta(val):
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:.1f}M"


# ── SECTIONS ─────────────────────────────────────────────────────────────

def _show_ten_questions(d) -> None:
    """The ten questions, answered from recorded history."""
    teach = {
        "Who won the game?": "teach-1",
        "Were the winner and the best model the same team?": "teach-2",
        "Did those overrides help or hurt?": "teach-3",
        "Did leverage create or destroy value?": "teach-2",
        "What should a student conclude?": "teach-1",
    }
    for a in d.answers:
        cls = teach.get(a.question, "")
        detail = f'<div class="d">{a.detail}</div>' if a.detail else ""
        st.markdown(
            f'<div class="qa-card {cls}">'
            f'<div class="q">{a.number}. {a.question}</div>'
            f'<div class="a">{a.answer}</div>'
            f"{detail}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _show_channels(d, starting_equity: float) -> None:
    """Where each fund's NAV change came from. The three channels sum exactly."""
    rows = []
    for c in d.channels:
        rows.append({
            "Fund": c.team_name,
            "NAV": f"${c.nav:,.2f}M",
            "Return": f"{c.cumulative_return:+.1%}",
            "Value change": f"${c.value_channel:+,.2f}M",
            "NOI income": f"${c.noi_income:+,.2f}M",
            "Interest paid": f"${-c.interest_paid:+,.2f}M",
            "Net carry": f"${c.net_carry:+,.2f}M",
            "Gross LTV": f"{c.gross_ltv:.0%}" if c.gross_ltv else "—",
            "Leverage": c.leverage_verdict,
            "Assets": c.assets,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(
        f"Check the arithmetic yourself: value change + NOI income − interest paid "
        f"equals NAV minus the ${starting_equity:,.0f}M every fund started with. "
        f"There are no other terms."
    )


def _show_analytics_board(d) -> None:
    rows = []
    for t in d.analytics:
        rows.append({
            "Fund": t.team_name,
            "Valuation MAE": f"${t.valuation_mae:.2f}M" if t.valuation_mae is not None else "—",
            "NOI growth MAE": f"{t.noi_growth_mae:.4f}" if t.noi_growth_mae is not None else "—",
            "Downside Brier": f"{t.downside_brier:.3f}" if t.downside_brier is not None else "—",
            "vs naive ask": f"{t.value_added_vs_naive:+.1%}" if t.value_added_vs_naive is not None else "—",
            "Assets won": t.properties_won,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(
        "This board is deliberately separate from the game leaderboard. It answers "
        "'was the analysis any good', not 'who won'. Note that 'vs naive ask' compares "
        "against valuing every property at its asking price — a benchmark that is hard "
        "to beat, because asking prices are close to fair on average."
    )


def _show_teaching_cases(d) -> None:
    """Which named cases actually occurred, with a concrete example of each."""
    for case, label in NAMED_CASES:
        count = d.case_counts.get(case, 0)
        ex = d.examples.get(case)
        cls = "present" if count else "absent"
        detail = ""
        if ex is not None:
            detail = (
                f" — e.g. <b>{ex.property_id}</b> round {ex.round_number + 1}, "
                f"{ex.team_id}"
            )
            if ex.realized_return is not None:
                detail += f", realized {ex.realized_return:+.1%}"
        st.markdown(
            f'<div class="case-row {cls}">'
            f'<span>{label}</span>'
            f'<span class="count">{count}{detail}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    if not d.case_counts.get("BAD DECISION + LUCKY REALIZED OUTCOME"):
        st.caption(
            "A case with no instances is reported as absent rather than manufactured. "
            "It appears as soon as some fund pays above the asking price and still "
            "makes money on the year."
        )


def _show_override_detail(gm) -> None:
    """Every recorded departure from a team's own stated policy."""
    any_records = False
    for team_id, team in gm.teams.items():
        records = getattr(team, "override_history", [])
        if not records:
            continue
        any_records = True
        with st.expander(f"{team.team_name} — {len(records)} override(s) recorded"):
            rows = []
            for o in records:
                rows.append({
                    "Property": o.property_id,
                    "Round": o.round_number + 1,
                    "Model max bid": f"${o.model_max_bid:,.2f}M",
                    "Actual bid": f"${o.actual_bid:,.2f}M",
                    "Bid override": f"${o.bid_override:+,.2f}M",
                    "Target LTV": f"{o.model_target_ltv:.1%}",
                    "Actual LTV": f"{o.actual_ltv:.1%}",
                    "LTV override": f"{o.ltv_override:+.1%}",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if not any_records:
        st.info(
            "No overrides were recorded: every fund bid at or below its own ceiling. "
            "The override question is then untested — consider having a team "
            "deliberately disagree with its model next time."
        )


def _show_attempts(gm, limit: int = 12) -> None:
    """Individual attempts, decomposed into model / decision / override / outcome."""
    attempts = assess_attempts(gm)
    if not attempts:
        st.caption("No attempts recorded.")
        return
    interesting = [a for a in attempts if a.case_labels] or attempts
    rows = []
    for a in interesting[:limit]:
        rows.append({
            "Round": a.round_number + 1,
            "Property": a.property_id,
            "Fund": gm.teams[a.team_id].team_name,
            "Model": a.model_label.replace("_", " ").title(),
            "Decision": a.decision_label.replace("_", " ").title(),
            "Override": a.override_label.replace("_", " ").title(),
            "Outcome": a.outcome_label.replace("_", " ").title(),
            "Realized": f"{a.realized_return:+.1%}" if a.realized_return is not None else "—",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _show_teaching_notes(gm) -> None:
    """The single most instructive attempt, in plain language."""
    attempts = [a for a in assess_attempts(gm) if a.case_labels and a.won]
    if not attempts:
        return
    order = {case: i for i, (case, _) in enumerate(NAMED_CASES)}
    attempts.sort(key=lambda a: order.get(a.case_label, 99))
    pick = attempts[0]
    st.markdown(
        f'<div class="interpretation">'
        f'<b>{gm.teams[pick.team_id].team_name}</b> on <b>{pick.property_id}</b> '
        f'(round {pick.round_number + 1}) — {pick.headline}. {pick.teaching_note()}'
        f"</div>",
        unsafe_allow_html=True,
    )


def _show_team_holdings(gm) -> None:
    for team_id, team in gm.teams.items():
        with st.expander(f"{team.team_name} — {len(team.properties)} asset(s)"):
            if not team.properties:
                st.caption("No assets acquired.")
                continue
            rows = []
            for pid, h in team.properties.items():
                rows.append({
                    "Property": pid,
                    "Type": h.property_type,
                    "Bought": f"${h.purchase_price:,.2f}M",
                    "Round": h.purchase_round + 1,
                    "Equity in": f"${h.equity_invested:,.2f}M",
                    "Debt": f"${h.debt_amount:,.2f}M",
                    "Debt rate": f"{h.debt_rate:.2%}",
                    "Current value": f"${h.current_value:,.2f}M",
                    "Unrealized": f"${h.current_value - h.purchase_price:+,.2f}M",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _show_strategy_evolution(reflections) -> None:
    if not reflections:
        st.caption("No in-game policy changes were recorded for this session.")
        return
    for rnum in sorted(reflections.keys(), key=lambda k: str(k)):
        st.markdown(
            f'<div class="strategy-row">'
            f'<span class="strategy-round">Round {rnum}</span>'
            f'<span class="strategy-change">{reflections[rnum]}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


# ── MAIN ─────────────────────────────────────────────────────────────────

def show():
    """Display the final debrief."""
    st.markdown(DEBRIEF_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="page-header">
        <h1>Final Debrief</h1>
        <p>Model quality, decision quality, and realized outcomes — kept separate on purpose</p>
    </div>
    """, unsafe_allow_html=True)

    gm = None
    if "game_manager" in st.session_state:
        gm = st.session_state.game_manager
    else:
        state = st.session_state.get("app_state")
        if state:
            gm = getattr(state, "game_manager", None)

    if not gm:
        st.error("No active game. Start one from the landing page or Professor Control.")
        return

    scored_rounds_done = len(getattr(gm, "round_history", {}))
    if not getattr(gm, "game_complete", False) and scored_rounds_done < gm.config.total_rounds:
        st.warning(
            f"Game is not complete yet — {scored_rounds_done} of "
            f"{gm.config.total_rounds} scored rounds resolved."
        )
        return

    d = debrief_answers(gm)

    # ── 1. THE TEN QUESTIONS ──
    st.markdown("<div class='section-header'>The ten questions</div>", unsafe_allow_html=True)
    st.caption("Every answer below is computed from recorded game history.")
    _show_ten_questions(d)

    # ── 2. STANDINGS ──
    st.markdown("<div class='section-header'>Final standings</div>", unsafe_allow_html=True)
    if d.standings:
        df = pd.DataFrame([
            {
                "Rank": i,
                "Fund": e["team_name"],
                "NAV": f"${e['nav']:,.2f}M",
                "Return": f"{e['cumulative_return']:+.1%}",
                "Cash": f"${e['cash']:,.2f}M",
                "Debt": f"${e['debt']:,.2f}M",
                "Assets": e["properties"],
            }
            for i, e in enumerate(d.standings, 1)
        ])
        st.dataframe(df, width="stretch", hide_index=True)

    # ── 3. WHERE THE MONEY CAME FROM ──
    st.markdown("<div class='section-header'>Where the money came from</div>",
                unsafe_allow_html=True)
    _show_channels(d, gm.config.starting_equity)

    # ── 4. ANALYTICS BOARD ──
    st.markdown("<div class='section-header'>Analytics leaderboard</div>",
                unsafe_allow_html=True)
    _show_analytics_board(d)

    # ── 5. TEACHING CASES ──
    st.markdown("<div class='section-header'>Model vs manager vs luck</div>",
                unsafe_allow_html=True)
    st.caption(
        "Decision quality is judged ex ante — against what was knowable before the "
        "outcome — so overriding your own model is not automatically a mistake."
    )
    _show_teaching_cases(d)
    _show_teaching_notes(gm)

    # ── 6. ATTEMPTS ──
    st.markdown("<div class='section-header'>Every attempt, decomposed</div>",
                unsafe_allow_html=True)
    _show_attempts(gm)

    # ── 7. OVERRIDES ──
    st.markdown("<div class='section-header'>Recorded overrides</div>",
                unsafe_allow_html=True)
    _show_override_detail(gm)

    # ── 8. PORTFOLIOS ──
    st.markdown("<div class='section-header'>Portfolios</div>", unsafe_allow_html=True)
    _show_team_holdings(gm)

    # ── 9. STRATEGY EVOLUTION ──
    st.markdown("<div class='section-header'>Strategy evolution</div>",
                unsafe_allow_html=True)
    _show_strategy_evolution(st.session_state.get("round_reflection", {}))

    st.markdown("---")
    if st.button("Back to the game", width="stretch"):
        st.session_state["game_complete"] = False
        st.rerun()


if __name__ == "__main__":
    show()
