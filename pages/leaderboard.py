"""
Leaderboard page showing game standings derived from GameManager.

Rankings derive from the same GameManager instance used by Live Game
and Professor Control. No synthetic data.
"""

import streamlit as st
import pandas as pd


def show():
    """Display the leaderboard derived from GameManager."""
    st.title("Leaderboard")
    st.caption("Game standings ranked by NAV")

    state = st.session_state.get("app_state")
    if not state:
        st.error("Application state not initialized. Please restart the demo.")
        return

    # Get GameManager
    gm = state.__dict__.get("game_manager")
    if not gm:
        st.warning("No active game. Start a game in Professor Control first.")
        return

    # Show game info
    round_display = "Practice" if gm.current_round == -1 else f"Round {gm.current_round + 1}"
    total_display = (
        gm.config.total_rounds + 1
        if gm.config.practice_round
        else gm.config.total_rounds
    )

    # Header metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Round", f"{round_display} of {total_display}")
    c2.metric(
        "State",
        gm.round_state.value.replace("_", " ").title(),
    )
    c3.metric("Teams", len(gm.teams))
    c4.metric("Scenario", gm.config.scenario)

    st.markdown("---")

    # Game leaderboard (sorted by NAV)
    st.header("🏆 Game Leaderboard")
    st.caption("Ranked by Ending Fund NAV")

    leaderboard = gm.get_leaderboard()
    if leaderboard:
        df = pd.DataFrame(leaderboard)
        df = df.sort_values("nav", ascending=False).reset_index(drop=True)
        df.index = df.index + 1

        # Format for display
        display = df.copy()
        display["Rank"] = display.index
        display["Team"] = display["team_name"]
        display["NAV ($M)"] = display["nav"].apply(lambda x: f"${x:.2f}")
        display["Cash ($M)"] = display["cash"].apply(lambda x: f"${x:.2f}")
        display["Debt ($M)"] = display["debt"].apply(lambda x: f"${x:.2f}")
        display["Properties"] = display["properties"]
        display["Return"] = display["cumulative_return"].apply(lambda x: f"{x:.1%}")

        st.dataframe(
            display[["Rank", "Team", "NAV ($M)", "Return", "Properties", "Cash ($M)", "Debt ($M)"]],
            use_container_width=True,
            hide_index=True,
        )

        if leaderboard:
            winner = leaderboard[0]
            st.success(
                f"🥇 Leader: {winner['team_name']} with ${winner['nav']:.2f}M NAV"
            )

        # Portfolio breakdown per team
        st.markdown("---")
        st.subheader("Portfolio Breakdown")
        for team_info in leaderboard:
            team_id = team_info["team_id"]
            team = gm.teams[team_id]
            with st.expander(f"{team.team_name} Portfolio ({len(team.properties)} properties)"):
                if team.properties:
                    portfolio_df = pd.DataFrame([
                        {
                            "Property": h.property_id,
                            "Purchase Price": f"${h.purchase_price:.2f}M",
                            "Current Value": f"${h.current_value:.2f}M",
                            "NOI": f"${h.current_noi:.2f}M",
                            "Return": f"{((h.current_value - h.purchase_price) / h.purchase_price):.1%}" if h.purchase_price > 0 else "N/A",
                            "Type": h.property_type,
                            "Submarket": h.submarket,
                        }
                        for h in team.properties.values()
                    ])
                    st.dataframe(portfolio_df, use_container_width=True)
                else:
                    st.info("No properties acquired yet.")

    else:
        st.info("No team data available.")

    # Analytics overview
    st.markdown("---")
    st.subheader("📊 Analytics Overview")

    # Show override tracking for teams that have it
    has_overrides = any(
        getattr(t, "override_history", []) for t in gm.teams.values()
    )
    if has_overrides:
        st.write("Override Summary:")
        override_rows = []
        for team_id, team in gm.teams.items():
            overrides = getattr(team, "override_history", [])
            if overrides:
                helpful = sum(
                    1
                    for o in overrides
                    if (o.bid_override > 0 and o.actual_bid > o.model_max_bid)
                    or (o.bid_override < 0 and o.actual_bid < o.model_max_bid)
                )
                override_rows.append(
                    {
                        "Team": team.team_name,
                        "Overrides": len(overrides),
                        "Helpful": helpful,
                        "Disciplined": len(overrides) - helpful,
                    }
                )
        if override_rows:
            ov_df = pd.DataFrame(override_rows)
            st.dataframe(ov_df, use_container_width=True, hide_index=True)
    else:
        st.info("No override data yet. Overrides are tracked when teams bid on properties with model predictions.")
