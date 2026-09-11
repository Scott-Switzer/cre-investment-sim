"""
Final Debrief page — model vs manager vs luck analysis.

Reads exclusively from GameManager: predictions, override history,
round history, and final team states.
"""

import streamlit as st
import pandas as pd


def show():
    """Display the final debrief."""
    st.title("Final Debrief")
    st.caption("Model quality, decision quality, and realized outcomes")

    state = st.session_state.get("app_state")
    if not state:
        st.error("Application state not initialized. Please restart the demo.")
        return

    # Check if game is complete
    gm = state.__dict__.get("game_manager")
    if not gm:
        st.warning("No active game.")
        return

    if not getattr(gm, "game_complete", False):
        st.warning("Game is not complete yet. Wait for all rounds to finish.")
        return

    st.header("🏆 Game Complete")

    # FINAL STANDINGS
    st.header("Final Standings")
    leaderboard = gm.get_leaderboard()
    if leaderboard:
        df = pd.DataFrame(leaderboard)
        df = df.sort_values("nav", ascending=False).reset_index(drop=True)
        df.index = df.index + 1

        display = df.copy()
        display["Rank"] = display.index
        display["Team"] = display["team_name"]
        display["Final NAV"] = display["nav"].apply(lambda x: f"${x:.2f}M")
        display["Return"] = display["cumulative_return"].apply(lambda x: f"{x:.1%}")
        display["Properties"] = display["properties"]
        display["Debt"] = display["debt"].apply(lambda x: f"${x:.2f}M")
        display["Cash"] = display["cash"].apply(lambda x: f"${x:.2f}M")

        st.dataframe(
            display[["Rank", "Team", "Final NAV", "Return", "Properties", "Debt", "Cash"]],
            use_container_width=True,
            hide_index=True,
        )

        # Winner banner
        if leaderboard:
            winner = leaderboard[0]
            st.success(f"🥇 **{winner['team_name']}** — ${winner['nav']:.2f}M NAV ({winner['cumulative_return']:.1%} return)")
        if len(leaderboard) > 1:
            second = leaderboard[1]
            st.info(f"🥈 **{second['team_name']}** — ${second['nav']:.2f}M NAV")
        if len(leaderboard) > 2:
            third = leaderboard[2]
            st.info(f"🥉 **{third['team_name']}** — ${third['nav']:.2f}M NAV")

    st.markdown("---")

    # MODEL VS MANAGER VS LUCK
    st.header("Model vs Manager vs Luck Analysis")

    st.info("""
    This analysis separates three dimensions:
    - **Model Quality:** How accurate were your predictions vs actual outcomes?
    - **Manager Quality:** Did you follow your model or make good overrides?
    - **Outcome:** What actually happened (can be good or bad regardless of decisions)
    """)

    for team_id, team in gm.teams.items():
        with st.expander(f"{team.team_name}", expanded=(team_id == list(gm.teams.keys())[0])):
            _show_team_analysis(gm, team)

    st.markdown("---")

    # ROUND-BY-ROUND BREAKDOWN
    st.header("Round-by-Round Breakdown")

    for round_num, result in gm.round_history.items():
        with st.expander(f"Round {round_num + 1}", expanded=True):
            # Market state
            ms = result.market_state
            cols = st.columns(4)
            cols[0].metric("Policy Rate", f"{ms.policy_rate:.2%}")
            cols[1].metric("Unemployment", f"{ms.unemployment:.2%}")
            cols[2].metric("Employment Growth", f"{ms.employment_growth:.2%}")
            cols[3].metric("Inflation", f"{ms.inflation:.2%}")

            st.write("**Auction Results:**")
            for prop_id, ar in result.auction_results.items():
                if ar.sold:
                    st.write(f"  ✅ {prop_id}: Sold to **{ar.winning_team_id}** for ${ar.winning_bid:.2f}M")
                else:
                    st.write(f"  ⬜ {prop_id}: Not sold (reserve: ${ar.reserve_price:.2f}M)")

            # Property outcomes
            st.write("**Property Outcomes:**")
            for prop_id, outcome in result.property_outcomes.items():
                st.write(f"  {prop_id}: NOI growth {outcome.noi_growth_actual:.1%}, Exit value ${outcome.exit_value:.2f}M")

    st.markdown("---")

    # KEY LEARNING INSIGHTS
    st.header("Key Learning Insights")
    st.markdown("""
    ### Takeaways

    1. **Model Discipline vs Human Judgment** — When did you override? Was it justified?
    2. **Capital Allocation** — Did early decisions limit later opportunities?
    3. **Risk Management** — Did downside predictions correlate with outcomes?
    4. **Competitive Dynamics** — Did you overpay? Underbid? Win properties you shouldn't have?
    5. **Model Improvement** — Which property types/submarkets was your model weakest on?
    """)


def _show_team_analysis(gm, team):
    """Show detailed analysis for one team."""
    cols = st.columns(3)

    with cols[0]:
        st.subheader("Model Quality")
        preds = team.model_predictions
        if preds:
            st.write(f"{len(preds)} properties with model predictions")
            avg_pred_val = sum(p.predicted_fair_value for p in preds.values()) / len(preds)
            avg_max_bid = sum(p.max_bid for p in preds.values()) / len(preds)
            st.metric("Avg Predicted Value", f"${avg_pred_val:.2f}M")
            st.metric("Avg Max Bid", f"${avg_max_bid:.2f}M")
        else:
            st.info("No model predictions uploaded")

    with cols[1]:
        st.subheader("Manager Quality")
        overrides = getattr(team, "override_history", [])
        if overrides:
            st.metric("Total Overrides", len(overrides))
            avg_override = sum(o.bid_override for o in overrides) / len(overrides)
            st.metric("Avg Bid Override", f"${avg_override:.2f}M")
            helpful = sum(
                1
                for o in overrides
                if abs(o.bid_override) > 0.5
            )
            st.metric("Significant Overrides", helpful)
        else:
            st.success("No overrides — followed model recommendations")

    with cols[2]:
        st.subheader("Outcome")
        st.metric("Final NAV", f"${team.nav:.2f}M")
        st.metric("Cumulative Return", f"{team.cumulative_return:.1%}")
        st.metric("Properties Acquired", len(team.properties))

    # Override breakdown table
    if overrides:
        st.markdown("---")
        st.subheader("Override Breakdown")
        rows = []
        for o in overrides:
            # Classify: bid higher than model max = aggressive, lower = conservative
            if o.bid_override > 0.5:
                action = "Aggressive (+${:.0f}M)".format(o.bid_override)
            elif o.bid_override < -0.5:
                action = "Conservative (${:.0f}M)".format(o.bid_override)
            else:
                action = "Aligned"

            rows.append({
                "Property": o.property_id,
                "Round": o.round_number + 1,
                "Model Max": f"${o.model_max_bid:.2f}M",
                "Actual": f"${o.actual_bid:.2f}M",
                "Override": f"${o.bid_override:.2f}M",
                "Action": action,
            })

        ov_df = pd.DataFrame(rows)
        st.dataframe(ov_df, use_container_width=True, hide_index=True)

    # Portfolio summary
    st.markdown("---")
    st.subheader("Portfolio Summary")
    if team.properties:
        pf_df = pd.DataFrame([
            {
                "Property": h.property_id,
                "Purchase": f"${h.purchase_price:.2f}M",
                "Current Value": f"${h.current_value:.2f}M",
                "NOI": f"${h.current_noi:.2f}M",
                "Type": h.property_type,
            }
            for h in team.properties.values()
        ])
        st.dataframe(pf_df, use_container_width=True, hide_index=True)
        total_value = sum(h.current_value for h in team.properties.values())
        st.metric("Portfolio Value", f"${total_value:.2f}M")
    else:
        st.info("No properties acquired.")
