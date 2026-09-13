"""
Live Game — unified game screen.

One persistent page that changes appearance based on GameManager state.
Model predictions displayed prominently beside each property.
No sidebar navigation during gameplay.
"""

from __future__ import annotations

import streamlit as st
from datetime import datetime

from src.game.adjudicator import RoundState, Bid
from src.game.manager import GameManager


# ─── CSS ──────────────────────────────────────────────────────────────────

_CSS = """
<style>
[data-testid="stExpander"] { border-radius: 8px; margin-bottom: 8px; }
.stMetric { padding: 4px 0; }
.game-header { text-align: center; padding: 12px 0 8px; }
.round-badge {
    display: inline-block;
    background: #1a5276;
    color: #fff;
    font-size: 1.3em;
    font-weight: 700;
    padding: 8px 28px;
    border-radius: 6px;
    letter-spacing: 1px;
}
.action-bar {
    display: flex;
    justify-content: center;
    gap: 12px;
    padding: 12px 0;
}
.status-open { color: #27ae60; }
.status-locked { color: #e74c3c; }
.status-resolved { color: #2980b9; }
.model-box {
    background: #f0f7ff;
    border-left: 3px solid #2980b9;
    padding: 10px 14px;
    margin: 8px 0;
    border-radius: 0 6px 6px 0;
}
.stat-sm { font-size: 0.85em; color: #555; }
</style>
"""


def show():
    st.markdown(_CSS, unsafe_allow_html=True)

    game_manager = st.session_state.get("game_manager")
    if not game_manager:
        _show_not_started()
        return

    team_name = st.session_state.get("current_team", "Your Fund")
    team_state = game_manager.teams.get(team_name)
    round_state = game_manager.round_state

    _render_top_bar(game_manager, team_name, team_state)

    if round_state == RoundState.NOT_STARTED:
        _render_not_started(game_manager, team_name, team_state)
    elif round_state == RoundState.OPEN:
        _render_round_open(game_manager, team_name)
    elif round_state == RoundState.LOCKED:
        _render_locked(game_manager, team_name)
    elif round_state == RoundState.RESOLVED:
        _render_results(game_manager, team_name)


# ─── Not started (pre-game / practice intro) ─────────────────────────────

def _show_not_started():
    st.title("REAL 605 — CRE Investment Simulation")
    st.info("Game has not started yet. Wait for the instructor to begin, or select **Try Demo** on the home page.")


def _render_not_started(gm: GameManager, team_name: str, team_state):
    st.title("REAL 605 — CRE Investment Simulation")

    if team_state:
        st.markdown(f"**{team_name}** · Capital: **${team_state.cash:.0f}M**")

    st.markdown("### Your Model Strategy")

    if team_state and team_state.model_predictions:
        st.markdown("""
        Your model has predicted fair values for today's properties.
        The game tests whether you **trust and use your analysis**.
        """)
        preds = sorted(
            team_state.model_predictions.values(),
            key=lambda p: (p.predicted_fair_value - p.max_bid),
            reverse=True,
        )
        for p in preds[:5]:
            st.caption(
                f"{p.property_id}: Fair Value **${p.predicted_fair_value:.1f}M** "
                f"· Max Bid **${p.max_bid:.1f}M**"
            )
    else:
        st.warning("No model predictions available. Upload a model on the "
                   "Strategy Card or Model Check-In page.")

    st.markdown("### How the game works")
    st.caption("""
    1. Each round, you see 4 properties with market data.
    2. Your model predicts fair value and a max bid for each.
    3. You decide: **PASS** or **BID** (at a price and LTV).
    4. Highest valid bid wins. Market evolves each round.
    5. Final ranking is by NAV — your portfolio's total value.
    """)

    if not gm.game_started and not gm.game_complete:
        if st.button("START GAME", type="primary", use_container_width=True,
                      key="live_start_game"):
            gm.start_game()
            st.rerun()


# ─── Round Open ───────────────────────────────────────────────────────────

def _render_round_open(gm: GameManager, team_name: str):
    practice = gm.current_round == -1
    if practice:
        badge_text = "PRACTICE ROUND"
    else:
        badge_text = f"ROUND {gm.current_round + 1} OF {gm.config.total_rounds}"

    st.markdown(
        f'<div class="game-header"><span class="round-badge">{badge_text}'
        f'</span></div>', unsafe_allow_html=True)
    st.caption("Submissions OPEN · Make your selections below")

    team_state = gm.teams.get(team_name)
    if team_state:
        cols = st.columns(5)
        cols[0].metric("Cash", f"${team_state.cash:.0f}M")
        cols[1].metric("NAV", f"${team_state.nav:.0f}M")
        cols[2].metric("Properties", len(team_state.properties))
        cols[3].metric("Debt", f"${team_state.debt:.0f}M")
        cols[4].metric("Return", f"{team_state.cumulative_return:.0%}")

    st.markdown("---")

    if gm.market_history:
        ms = gm.market_history[-1]
        st.caption(
            f"Market: Rate {ms.policy_rate:.2%} · "
            f"Unemp {ms.unemployment:.1%} · "
            f"Infl {ms.inflation:.1%}"
        )
    else:
        st.caption("Market: Base case assumptions")

    st.markdown("---")
    st.subheader("Market")

    for prop_id, prop in gm.current_properties.items():
        _render_deal_card(gm, team_name, prop_id, prop)

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    if st.button("SUBMIT ALL DECISIONS", type="primary",
                  use_container_width=True, key="live_submit_all"):
        _submit_all(gm, team_name)


def _render_deal_card(gm: GameManager, team_name: str,
                      prop_id: str, prop):
    """One deal card: market → model → decision."""
    with st.expander(f"{prop.property_name}", expanded=True):
        cols = st.columns([3, 2])

        with cols[0]:
            st.markdown(f"**{prop.property_type}** · {prop.submarket}")
            st.caption(
                f"Building: {prop.building_sf:,.0f} SF · Year: {prop.year_built}"
            )
            st.markdown(f"""
            <span class="stat-sm">Ask &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${prop.asking_price:.1f}M</span>
            <span class="stat-sm">NOI&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${prop.current_noi:.2f}M</span>
            <span class="stat-sm">Cap &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {prop.current_cap:.1%}</span>
            <span class="stat-sm">Occupancy&nbsp; {prop.occupancy:.1%}</span>
            """, unsafe_allow_html=True)

        with cols[1]:
            team_state = gm.teams.get(team_name)
            if team_state and prop_id in team_state.model_predictions:
                mp = team_state.model_predictions[prop_id]
                discount_pct = (
                    (mp.predicted_fair_value - prop.asking_price)
                    / prop.asking_price * 100
                )
                st.markdown('<div class="model-box">', unsafe_allow_html=True)
                st.markdown("**YOUR MODEL**")
                st.caption(
                    f"Fair Value: **${mp.predicted_fair_value:.1f}M**"
                )
                st.caption(f"Max Bid: **${mp.max_bid:.1f}M**")
                if discount_pct > 0:
                    st.caption(f"↗ {discount_pct:.0f}% upside to ask")
                else:
                    st.caption(f"↘ {abs(discount_pct):.0f}% over ask")
                st.caption(
                    f"Target LTV: {mp.target_ltv:.0%} · "
                    f"Downside: {mp.probability_of_downside:.0%}"
                )
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.caption("No model prediction for this property.")

        decision_key = f"_dec_{prop_id}"
        if decision_key not in st.session_state:
            st.session_state[decision_key] = "PASS"
        d = st.radio(
            "Your Decision", ["PASS", "BID"],
            key=decision_key, horizontal=True,
        )

        if d == "BID":
            bid_key = f"_bid_{prop_id}"
            ltv_key = f"_ltv_{prop_id}"
            if bid_key not in st.session_state:
                st.session_state[bid_key] = prop.asking_price * 0.95
            if ltv_key not in st.session_state:
                st.session_state[ltv_key] = 0.60

            bc, lc = st.columns(2)
            with bc:
                bid_price = st.number_input(
                    "Bid ($M)", min_value=0.0, max_value=500.0,
                    value=float(st.session_state[bid_key]),
                    step=0.5, format="%.1f", key=bid_key,
                )
            with lc:
                bid_ltv = st.number_input(
                    "LTV", min_value=0.0, max_value=prop.max_ltv,
                    value=float(st.session_state[ltv_key]),
                    step=0.05, format="%.2f", key=ltv_key,
                )

            equity_req = bid_price * (1 - bid_ltv)
            avail = team_state.cash if team_state else 0
            if equity_req > avail:
                st.error(
                    f"Insufficient equity: need ${equity_req:.1f}M, "
                    f"have ${avail:.1f}M"
                )
            else:
                st.success(f"Equity required: ${equity_req:.1f}M")
        else:
            st.info("Passing on this property.")


# ─── Locked ───────────────────────────────────────────────────────────────

def _render_locked(gm: GameManager, team_name: str):
    practice = gm.current_round == -1
    if practice:
        st.markdown(
            '<div class="game-header">'
            '<span class="round-badge">PRACTICE</span></div>',
            unsafe_allow_html=True,
        )
        st.caption("Decisions locked · Awaiting results")
    else:
        rnum = gm.current_round + 1
        st.markdown(
            f'<div class="game-header">'
            f'<span class="round-badge">ROUND {rnum} LOCKED</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Round {rnum} of {gm.config.total_rounds} · "
            "Awaiting market close"
        )
    st.caption("Waiting for the instructor to resolve the round.")

    st.markdown("---")
    st.subheader("Your Decisions")

    submitted = [b for b in gm.submitted_bids if b.team_id == team_name]
    if submitted:
        for bid in submitted:
            with st.expander(bid.property_id):
                st.write(
                    f"**BID** ${bid.bid_price:.1f}M · LTV {bid.ltv:.0%}"
                )
    else:
        st.info("No decisions submitted.")


# ─── Resolved / Results ──────────────────────────────────────────────────

def _render_results(gm: GameManager, team_name: str):
    result = gm.current_round_result
    if not result:
        st.info("Results not yet available.")
        return

    practice = gm.current_round == -1
    if practice:
        st.markdown(
            '<div class="game-header">'
            '<span class="round-badge">PRACTICE COMPLETE</span></div>',
            unsafe_allow_html=True,
        )
        st.caption("This round does not count. Ready for the real game?")
    else:
        rnum = gm.current_round + 1
        st.markdown(
            f'<div class="game-header">'
            f'<span class="round-badge">ROUND {rnum} RESULTS</span></div>',
            unsafe_allow_html=True,
        )

    team_state = gm.teams.get(team_name)
    if team_state:
        st.markdown("---")
        cols = st.columns(4)
        cols[0].metric("Cash", f"${team_state.cash:.0f}M")
        cols[1].metric("NAV", f"${team_state.nav:.0f}M")
        cols[2].metric("Properties", len(team_state.properties))
        cols[3].metric("Cumulative Return",
                       f"{team_state.cumulative_return:.1%}")

    st.markdown("---")
    st.subheader("Auction Results")

    for prop_id, auction in result.auction_results.items():
        with st.expander(prop_id):
            if auction.sold:
                if auction.winning_team_id == team_name:
                    st.success(
                        f"🎉 You won for **${auction.winning_bid:.1f}M**"
                    )
                    if team_state and prop_id in team_state.properties:
                        h = team_state.properties[prop_id]
                        st.write(
                            f"Holding: "
                            f"${h.current_value:.1f}M · "
                            f"${h.current_noi:.2f}M NOI"
                        )
                else:
                    st.info(
                        f"Sold to {auction.winning_team_id} "
                        f"for **${auction.winning_bid:.1f}M**"
                    )
            else:
                st.warning(
                    f"Not sold (reserve: "
                    f"${auction.reserve_price:.1f}M)"
                )

    if result.property_outcomes:
        st.subheader("Property Outcomes")
        for prop_id, outcome in result.property_outcomes.items():
            with st.expander(prop_id):
                st.caption(
                    f"NOI growth: {outcome.noi_growth_actual:.1%} · "
                    f"Exit cap: {outcome.cap_rate_actual:.1%} · "
                    f"Exit value: ${outcome.exit_value:.1f}M"
                )

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    if not practice:
        if st.button("CONTINUE TO NEXT ROUND", type="primary",
                      use_container_width=True, key="live_continue"):
            gm.advance_round()
            st.rerun()
    else:
        if st.button("START REAL GAME", type="primary",
                      use_container_width=True, key="live_practice_done"):
            gm.advance_round()
            st.rerun()


# ─── Submission ───────────────────────────────────────────────────────────

def _submit_all(gm: GameManager, team_name: str):
    """Collect decisions and submit all bids at once."""
    submitted = []
    errors = []
    team_state = gm.teams.get(team_name)

    for prop_id, prop in gm.current_properties.items():
        decision_key = f"_dec_{prop_id}"
        decision = st.session_state.get(decision_key, "PASS")

        if decision == "BID":
            bid_key = f"_bid_{prop_id}"
            ltv_key = f"_ltv_{prop_id}"

            try:
                bid = Bid(
                    team_id=team_name,
                    property_id=prop_id,
                    bid_price=float(
                        st.session_state.get(bid_key, prop.asking_price)
                    ),
                    ltv=float(st.session_state.get(ltv_key, 0.6)),
                    round_number=gm.current_round,
                    timestamp=datetime.now().isoformat(),
                    confidence=0.8,
                )
                gm.submit_bid(bid)
                submitted.append(prop_id)
            except (ValueError, RuntimeError) as e:
                errors.append(f"{prop_id}: {e}")

    if errors:
        for err in errors:
            st.error(f"❌ {err}")
    else:
        st.success(
            f"✅ {len(submitted)} decision(s) locked in. "
            "Awaiting market close."
        )
        for prop_id in submitted:
            st.session_state[f"_dec_{prop_id}"] = "PASS"


# ─── Top bar ──────────────────────────────────────────────────────────────

def _render_top_bar(gm: GameManager, team_name: str, team_state):
    """Persistent top bar."""
    cols = st.columns(6)

    with cols[0]:
        st.markdown(f"**{team_name}**")

    with cols[1]:
        if gm.game_complete:
            st.caption("GAME COMPLETE")
        elif gm.current_round == -1:
            st.caption("Practice")
        else:
            st.caption(f"Round {gm.current_round + 1} of {gm.config.total_rounds}")

    with cols[2]:
        rs = gm.round_state
        labels = {
            RoundState.NOT_STARTED: "⏳ Ready",
            RoundState.OPEN: "🟢 Open",
            RoundState.LOCKED: "🔒 Locked",
            RoundState.RESOLVED: "✅ Resolved",
        }
        st.caption(labels.get(rs, str(rs)))

    with cols[3]:
        cash = team_state.cash if team_state else 0
        st.metric("Cash", f"${cash:.0f}M")

    with cols[4]:
        nav = team_state.nav if team_state else 0
        st.metric("NAV", f"${nav:.0f}M")

    with cols[5]:
        holdings = len(team_state.properties) if team_state else 0
        st.metric("Holdings", holdings)

    st.markdown("---")


if __name__ == "__main__":
    show()
