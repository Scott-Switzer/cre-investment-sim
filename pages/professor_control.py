"""
Professor Control — game management and Try Demo mode.

In classroom mode: professor controls the round lifecycle for all teams.
Try Demo mode: reviewer plays as Your Fund against 3 bots,
manually advancing through rounds without a professor.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.game.adjudicator import RoundState


def show():
    st.title("Professor Control")
    st.caption("Instructor view: manage rounds, view standings")

    game_manager = st.session_state.get("game_manager")

    # ── Try Demo button ──────────────────────────────────────────────
    if game_manager is None:
        st.markdown("### Start Game")
        st.markdown(
            "Choose **Try Demo** to play as Your Fund against 3 bots, "
            "or **Setup Custom Game** for instructor mode."
        )
        if st.button("TRY DEMO", type="primary", use_container_width=True,
                      key="pc_try_demo"):
            _init_demo()
            st.rerun()

        st.markdown("---")
        st.subheader("Setup Custom Game")
        _render_setup_form()

    else:
        gm = game_manager
        st.success(f"Game running: {len(gm.teams)} teams")

        # ── Try Demo auto-advance ────────────────────────────────────
        if st.session_state.get("demo_mode", False):
            st.markdown("### Demo Controls")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Auto-Advance Next Round", type="primary",
                              use_container_width=True,
                              key="pc_auto_advance"):
                    _auto_advance(gm)
            with col2:
                if st.button("Resolve Round", use_container_width=True,
                              key="pc_resolve"):
                    _resolve_current(gm)

        # ── Round status ─────────────────────────────────────────────
        _render_round_status(gm)

        # ── Professor controls ───────────────────────────────────────
        if not st.session_state.get("demo_mode", False):
            st.markdown("---")
            st.subheader("Round Actions")
            _render_professor_actions(gm)

        # ── Leaderboard ──────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Team Standings")
        _render_leaderboard(gm)

        # ── End game / restart ───────────────────────────────────────
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reset Demo", type="secondary",
                          use_container_width=True):
                from src.utils.state import restart_demo
                restart_demo()
                st.rerun()
        with col2:
            if st.button("End Game Early", use_container_width=True,
                          key="pc_end_early"):
                gm.game_complete = True
                st.session_state["game_complete"] = True
                gm.log("Game ended early")
                st.success("Game ended. Check Leaderboard and Final Debrief.")
                st.rerun()


def _init_demo():
    """Initialize a demo game with 3 bots + Your Fund."""
    from src.game.manager import GameManager, GameConfig
    from scripts.create_demo_teams import create_demo_teams
    from src.game.adjudicator import ModelPrediction

    config = GameConfig(
        seed=20240331,
        starting_equity=100.0,
        total_rounds=4,
        properties_per_round=4,
        practice_round=True,
        scenario="Base Case",
    )

    gm = GameManager(config)

    demo_preds = create_demo_teams(seed=20240331, count=120)

    bot_count = 0
    for team_name, predictions_df in demo_preds.items():
        if bot_count >= 3:
            break
        model_preds = {}
        for _, row in predictions_df.iterrows():
            model_preds[str(row["property_id"])] = ModelPrediction(
                property_id=str(row["property_id"]),
                predicted_fair_value=float(row["predicted_fair_value"]),
                predicted_noi_growth=float(row["predicted_noi_growth"]),
                probability_of_downside=float(
                    row.get("probability_of_downside", 0.2) or 0.2
                ),
                max_bid=float(row["max_bid"]),
                target_ltv=float(row["target_ltv"]),
                model_name=str(row["model_name"]),
                confidence=float(row.get("confidence", 0.8) or 0.8),
                predicted_exit_cap=float(
                    row.get("predicted_exit_cap", 0.06) or 0.06
                ),
            )
        gm.add_team(team_name, team_name, model_preds)
        bot_count += 1

    # Add Your Fund
    gm.add_team("Your Fund", "Your Fund")

    gm.start_game()

    st.session_state["game_manager"] = gm
    st.session_state["game_started"] = True
    st.session_state["game_complete"] = False
    st.session_state["demo_mode"] = True
    st.session_state["current_team"] = "Your Fund"
    st.success("Demo started! Play as **Your Fund** on the Live Game page.")


def _auto_advance(gm):
    """Auto-advance through round lifecycle in Try Demo mode."""
    rs = gm.round_state

    if rs == RoundState.NOT_STARTED:
        gm.round_state = RoundState.OPEN
    elif rs == RoundState.OPEN:
        try:
            gm.lock_round()
            st.session_state["round_state"] = RoundState.LOCKED
            gm.log("Round locked (auto)")
        except RuntimeError:
            pass
    elif rs == RoundState.LOCKED:
        try:
            result = gm.resolve_round()
            st.session_state["last_round_result"] = result
            st.session_state["round_state"] = RoundState.RESOLVED
            gm.log("Round resolved (auto)")
            st.success(f"Round resolved: {len(result.auction_results)} properties")
            st.rerun()
        except Exception as e:
            st.error(f"Resolve failed: {e}")
            return
    elif rs == RoundState.RESOLVED:
        try:
            gm.advance_round()
            st.session_state["game_manager"] = gm
            if gm.game_complete:
                st.session_state["game_complete"] = True
                gm.log("Game complete (auto)")
                st.success("🎉 Game Complete! Check Leaderboard and Final Debrief.")
            else:
                st.success("Advanced to next round.")
            st.rerun()
        except RuntimeError as e:
            st.error(f"Advance failed: {e}")
            return


def _resolve_current(gm):
    """Resolve current round (Try Demo convenience)."""
    if gm.round_state == RoundState.LOCKED:
        try:
            result = gm.resolve_round()
            st.session_state["last_round_result"] = result
            st.session_state["round_state"] = RoundState.RESOLVED
            gm.log("Round resolved")
            st.success(f"Resolved: {len(result.auction_results)} properties")
            st.rerun()
        except Exception as e:
            st.error(f"Resolve failed: {e}")


def _render_setup_form():
    """Render the professor game setup form."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        scenario = st.selectbox(
            "Scenario",
            ["Base Case", "Rate Shock", "Growth Rebound"],
            index=0, key="pc_scenario",
        )
    with col2:
        starting_equity = st.number_input(
            "Starting Equity ($MM)", min_value=50.0,
            max_value=500.0, value=100.0, step=10.0, key="pc_equity",
        )
    with col3:
        total_rounds = st.number_input(
            "Total Rounds", min_value=3, max_value=6,
            value=4, step=1, key="pc_rounds",
        )
    with col4:
        seed = st.number_input(
            "Seed", min_value=0, value=20240331, step=1, key="pc_seed",
        )

    col1, col2 = st.columns(2)
    with col1:
        practice_round = st.checkbox(
            "Include Practice Round", value=True, key="pc_practice",
        )
    with col2:
        use_demo_teams = st.checkbox(
            "Use Demo Teams (4 bots)", value=True, key="pc_demo_teams",
        )

    if st.button("Start / Restart Game", type="primary",
                  use_container_width=True):
        from src.game.manager import GameManager, GameConfig
        from src.game.adjudicator import ModelPrediction
        from scripts.create_demo_teams import create_demo_teams

        config = GameConfig(
            seed=seed,
            starting_equity=starting_equity,
            total_rounds=total_rounds,
            properties_per_round=4,
            practice_round=practice_round,
            scenario=scenario,
        )

        game_manager = GameManager(config)

        if use_demo_teams:
            demo_preds = create_demo_teams(seed=seed, count=120)

            for team_name, predictions_df in demo_preds.items():
                model_preds = {}
                for _, row in predictions_df.iterrows():
                    model_preds[str(row["property_id"])] = ModelPrediction(
                        property_id=str(row["property_id"]),
                        predicted_fair_value=float(
                            row["predicted_fair_value"]
                        ),
                        predicted_noi_growth=float(
                            row["predicted_noi_growth"]
                        ),
                        probability_of_downside=float(
                            row.get("probability_of_downside", 0.2) or 0.2
                        ),
                        max_bid=float(row["max_bid"]),
                        target_ltv=float(row["target_ltv"]),
                        model_name=str(row["model_name"]),
                        confidence=float(
                            row.get("confidence", 0.8) or 0.8
                        ),
                        predicted_exit_cap=float(
                            row.get("predicted_exit_cap", 0.06) or 0.06
                        ),
                    )
                game_manager.add_team(team_name, team_name, model_preds)
        else:
            for i in range(1, 5):
                game_manager.add_team(f"Team {i}", f"Team {i}")

        game_manager.start_game()

        st.session_state["game_manager"] = game_manager
        st.session_state["game_started"] = True
        st.session_state["game_complete"] = False
        st.session_state["current_team"] = "Your Fund"
        st.session_state["demo_mode"] = False

        game_manager.log(
            "game started",
            scenario=scenario,
            seed=seed,
            starting_equity=starting_equity,
        )
        st.success(
            f"Game started with {len(game_manager.teams)} teams. "
            f"Scenario: {scenario}. Seed: {seed}."
        )


def _render_round_status(gm):
    """Display current round status."""
    round_display = (
        "Practice" if gm.current_round == -1
        else f"Round {gm.current_round + 1}"
    )
    total_display = (
        f"{gm.config.total_rounds + 1}"
        if gm.config.practice_round
        else str(gm.config.total_rounds)
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Round", f"{round_display} of {total_display}")
    col2.metric("State", gm.round_state.value.replace("_", " ").title())
    col3.metric("Teams", len(gm.teams))
    col4.metric("Scenario", gm.config.scenario)


def _render_professor_actions(gm):
    """Render professor round control buttons."""
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Open Round for Bidding", use_container_width=True):
            if gm.round_state != RoundState.NOT_STARTED:
                st.warning("Round is already in progress.")
            else:
                gm.round_state = RoundState.OPEN
                st.session_state["round_state"] = RoundState.OPEN
                gm.log("Round opened for bidding")
                st.success("Round is now OPEN for submissions.")

    with c2:
        if st.button("Lock Round", use_container_width=True):
            if gm.round_state != RoundState.OPEN:
                st.error("Round must be OPEN to lock.")
            else:
                try:
                    gm.lock_round()
                    st.session_state["round_state"] = RoundState.LOCKED
                    gm.log("Round locked")
                    st.success("Round is now LOCKED.")
                except RuntimeError as e:
                    st.error(f"Lock failed: {e}")

    with c3:
        if st.button("Resolve Round", type="primary",
                      use_container_width=True):
            if gm.round_state != RoundState.LOCKED:
                st.error("Round must be LOCKED before resolution.")
            else:
                try:
                    result = gm.resolve_round()
                    st.session_state["last_round_result"] = result
                    st.session_state["round_state"] = RoundState.RESOLVED
                    gm.log("Round resolved")
                    st.success("Round resolved.")

                    with st.expander("Resolution Summary", expanded=True):
                        for prop_id, ar in result.auction_results.items():
                            if ar.sold:
                                st.write(
                                    f"  {prop_id}: "
                                    f"Sold to {ar.winning_team_id} "
                                    f"for ${ar.winning_bid:.2f}M"
                                )
                            else:
                                st.write(
                                    f"  {prop_id}: "
                                    f"Not sold (reserve: "
                                    f"${ar.reserve_price:.2f}M)"
                                )
                except Exception as e:
                    st.error(f"Error resolving: {e}")

    st.markdown("---")

    if st.button("Advance to Next Round", use_container_width=True):
        if gm.round_state != RoundState.RESOLVED:
            st.error("Round must be RESOLVED before advancing.")
        else:
            try:
                gm.advance_round()
                st.session_state["game_manager"] = gm
                if gm.game_complete:
                    st.session_state["game_complete"] = True
                    gm.log("Game complete")
                    st.success(
                        "🎉 Game Complete! Navigate to Leaderboard "
                        "and Final Debrief."
                    )
                else:
                    next_round = (
                        "Practice"
                        if gm.current_round == -1
                        else f"Round {gm.current_round + 1}"
                    )
                    gm.log(f"Advanced to {next_round}")
                    st.success(f"Advanced to {next_round}.")
            except RuntimeError as e:
                st.error(f"Advance failed: {e}")


def _render_leaderboard(gm):
    """Display current leaderboard."""
    if gm.teams:
        leaderboard = []
        for tid, ts in gm.teams.items():
            leaderboard.append({
                "Team": tid,
                "NAV": f"${ts.nav:.2f}M",
                "Cash": f"${ts.cash:.2f}M",
                "Debt": f"${ts.debt:.2f}M",
                "Properties": len(ts.properties),
                "Return": f"{ts.cumulative_return:.1%}",
            })

        df = pd.DataFrame(leaderboard)
        df = df.sort_values("NAV", ascending=False).reset_index(drop=True)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("No team data available. Start a game to see standings.")


if __name__ == "__main__":
    show()
