"""
Leaderboard page showing game standings derived from GameManager.

Institutional CRE style — ranked by NAV, analytics separate from rankings.
"""

import streamlit as st
import pandas as pd


LEADERBOARD_CSS = """
<style>
.stApp {
    background: #f7fafc;
    color: #2d3748;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.stApp > header {
    background: #fff !important;
    border-bottom: 2px solid #1a365d !important;
}
.page-header {
    padding: 16px 0 12px 0;
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 20px;
}
.page-header h1 {
    font-size: 1.6em;
    font-weight: 700;
    color: #1a365d;
    margin: 0 0 2px 0;
}
.page-header p {
    font-size: 0.9em;
    color: #718096;
    margin: 0;
}
.section-header {
    font-size: 1em;
    font-weight: 700;
    color: #1a365d;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 2px solid #1a365d;
    padding-bottom: 4px;
    margin: 24px 0 12px 0;
}
.leaderboard-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
}
.leaderboard-table th {
    background: #1a365d;
    color: #fff;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.7em;
    letter-spacing: 0.04em;
    padding: 8px 10px;
    border: none;
    text-align: center;
}
.leaderboard-table td {
    padding: 10px;
    border-bottom: 1px solid #e2e8f0;
    text-align: center;
    font-variant-numeric: tabular-nums;
}
.leaderboard-table td:first-child { font-weight: 700; }
.leaderboard-table tr:nth-child(even) { background: #f7fafc; }
.leaderboard-table tr:nth-child(1) { background: #fefce8; }
.leaderboard-table tr:nth-child(1) td { font-weight: 700; }
.info-panel {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 14px;
    margin: 8px 0;
}
.data-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid #edf2f7;
    font-size: 0.85em;
}
.data-row:last-child { border-bottom: none; }
.data-label { color: #4a5568; }
.data-value { font-weight: 600; font-variant-numeric: tabular-nums; }
[data-testid="stSidebar"] {
    background: #fff !important;
    border-right: 1px solid #e2e8f0;
}
.stButton > button {
    background: #1a365d !important;
    color: #fff !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    font-size: 0.9em !important;
}
.stButton > button:hover {
    background: #2c5282 !important;
}
</style>
"""


def show():
    """Display the leaderboard derived from GameManager."""
    st.markdown(LEADERBOARD_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="page-header">
        <h1>Game Standings</h1>
        <p>Ranked by fund NAV</p>
    </div>
    """, unsafe_allow_html=True)

    # Get GameManager from session state
    gm = None
    if "game_manager" in st.session_state:
        gm = st.session_state.game_manager
    else:
        state = st.session_state.get("app_state")
        if state:
            gm = state.__dict__.get("game_manager")

    if not gm:
        st.error("No active game. Start a game in Professor Control or the main app.")
        return

    # Game info
    round_display = "Practice" if gm.current_round == -1 else f"Round {gm.current_round + 1}"
    total_display = (
        gm.config.total_rounds + 1
        if gm.config.practice_round
        else gm.config.total_rounds
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Round", f"{round_display} of {total_display}")
    c2.metric("State", gm.round_state.value.replace("_", " ").title())
    c3.metric("Teams", len(gm.teams))
    c4.metric("Scenario", gm.config.scenario)

    st.markdown("<div class='section-header'>Rankings</div>", unsafe_allow_html=True)

    leaderboard = gm.get_leaderboard()
    if leaderboard:
        st.markdown("""
        <table class="leaderboard-table">
            <tr>
                <th>Rank</th><th>Fund</th><th>NAV</th><th>Return</th>
                <th>Properties</th><th>Cash</th><th>Debt</th>
            </tr>
        """, unsafe_allow_html=True)

        df = pd.DataFrame(leaderboard)
        df = df.sort_values("nav", ascending=False).reset_index(drop=True)

        for i, entry in df.iterrows():
            st.markdown(
                f"<tr>"
                f"<td>{i+1}</td>"
                f"<td>{entry['team_name']}</td>"
                f"<td>${entry['nav']:.2f}M</td>"
                f"<td>{entry['cumulative_return']:.1%}</td>"
                f"<td>{entry['properties']}</td>"
                f"<td>${entry['cash']:.2f}M</td>"
                f"<td>${entry['debt']:.2f}M</td>"
                f"</tr>", unsafe_allow_html=True)

        st.markdown("</table>", unsafe_allow_html=True)
    else:
        st.info("No team data available yet.")

    # Analytics overview
    st.markdown("<div class='section-header'>Analytics</div>", unsafe_allow_html=True)

    has_overrides = any(
        getattr(t, "override_history", []) for t in gm.teams.values()
    )
    if has_overrides:
        st.markdown("<h4 style='font-size:0.85em;font-weight:600;margin:0 0 8px 0;'>Override Tracking</h4>",
                    unsafe_allow_html=True)
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
                override_rows.append({
                    "Team": team.team_name,
                    "Overrides": len(overrides),
                    "Helpful": helpful,
                    "Disciplined": len(overrides) - helpful,
                })
        if override_rows:
            ov_df = pd.DataFrame(override_rows)
            st.dataframe(ov_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No override data yet. Overrides are tracked when teams bid with model predictions.")

    st.markdown("<div class='section-header'>Portfolio Breakdown</div>", unsafe_allow_html=True)
    for team_id, team in gm.teams.items():
        if team.properties:
            with st.expander(f"{team.team_name} — {len(team.properties)} properties"):
                portfolio_df = pd.DataFrame([
                    {
                        "Property": h.property_id,
                        "Purchase": f"${h.purchase_price:.2f}M",
                        "Value": f"${h.current_value:.2f}M",
                        "NOI": f"${h.current_noi:.2f}M",
                        "Type": h.property_type,
                        "Submarket": h.submarket,
                    }
                    for h in team.properties.values()
                ])
                st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
    else:
        for team_id, team in gm.teams.items():
            st.caption(f"{team.team_name}: no properties acquired")


    st.markdown("---")
    if st.button("Back to Game", use_container_width=True):
        st.switch_page("app.py")


if __name__ == "__main__":
    show()
