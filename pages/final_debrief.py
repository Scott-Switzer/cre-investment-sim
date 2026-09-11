"""
Final Debrief — institutional CRE style.
Separates model quality, manager behavior, and outcomes.
"""

import streamlit as st
import pandas as pd

DEBRIEF_CSS = """
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
.data-value.positive {
    color: #276749;
}
.data-value.negative {
    color: #9b2c2c;
}
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
.matrix-cell.correct-followed {
    background: #f0fff4;
    border-color: #9ae6b4;
}
.matrix-cell.correct-overridden {
    background: #fffff0;
    border-color: #f6e05e;
}
.matrix-cell.wrong-followed {
    background: #fff5f5;
    border-color: #feb2b2;
}
.matrix-cell.wrong-override-success {
    background: #ebf8ff;
    border-color: #90cdf4;
}
.matrix-cell h5 {
    margin: 0 0 0.25rem 0;
    font-size: 0.85rem;
    font-weight: 600;
}
.strategy-row {
    display: flex;
    align-items: center;
    padding: 0.25rem 0;
    border-bottom: 1px solid #edf2f7;
}
.strategy-round {
    font-weight: 600;
    color: #1a365d;
    min-width: 60px;
}
.strategy-change {
    color: #4a5568;
}
</style>
"""

# ── HELPER FUNCTIONS ──

def fmt_currency(val, precision=2):
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:,.{precision}f}M"


def fmt_pct(val):
    return f"{val:.1%}"


def fmt_delta(val):
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:.1f}M"


def _interpret_override(override):
    if abs(override) < 0.5:
        return "Trusted model"
    elif override > 0:
        return "More aggressive"
    else:
        return "Less aggressive"


def _find_best_and_worst(gm):
    best_nav = 0
    best_decision = None
    worst_loss = 0
    worst_decision = None

    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        for o in overrides:
            # Best decision
            value_created = o.model_actual - o.actual_bid
            if value_created > best_nav:
                best_nav = value_created
                best_decision = {
                    "team": team.team_name,
                    "property": o.property_id,
                    "bid": o.actual_bid,
                    "model_max": o.model_max_bid,
                    "actual": o.model_actual,
                    "value_created": value_created,
                }
            # Worst decision
            value_destroyed = o.actual_bid - o.model_actual
            if value_destroyed > worst_loss:
                worst_loss = value_destroyed
                worst_decision = {
                    "team": team.team_name,
                    "property": o.property_id,
                    "bid": o.actual_bid,
                    "actual": o.model_actual,
                    "loss": value_destroyed,
                }

    if best_decision:
        st.markdown('<div class="debrief-section">', unsafe_allow_html=True)
        st.markdown(f"**{best_decision['team']}** on {best_decision['property']}")
        st.markdown(
            f"Purchased for <strong>{fmt_currency(best_decision['bid'])}</strong>, "
            f"actual value <strong>{fmt_currency(best_decision['actual'])}</strong>, "
            f"value created <strong style='color:#276749'>{fmt_delta(best_decision['value_created'])}</strong>"
        )
        st.markdown(
            f"Model suggested max <strong>{fmt_currency(best_decision['model_max'])}</strong> "
            f"— team {'overpaid' if best_decision['bid'] > best_decision['model_max'] else 'outperformed model'}"
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if worst_decision:
        st.markdown('<div class="debrief-section">', unsafe_allow_html=True)
        st.markdown(f"**{worst_decision['team']}** on {worst_decision['property']}")
        st.markdown(
            f"Purchased for <strong>{fmt_currency(worst_decision['bid'])}</strong>, "
            f"actual value <strong>{fmt_currency(worst_decision['actual'])}</strong>, "
            f"value destroyed <strong style='color:#9b2c2c'>{fmt_delta(worst_decision['loss'])}</strong>"
        )
        st.markdown("</div>", unsafe_allow_html=True)


def _show_model_matrix(gm, leaderboard):
    st.markdown('<div class="model-matrix">', unsafe_allow_html=True)
    
    # Collect all acquisitions
    cases = {
        "Model Correct + Followed Model": [],
        "Model Correct + Overridden": [],
        "Model Wrong + Followed Model": [],
        "Model Wrong + Overridden Successfully": [],
    }
    
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        for o in overrides:
            # Model correct if actual >= fair value estimate
            model_correct = o.model_actual >= o.model_pred * 0.95
            # Followed model if override is small
            followed = abs(o.bid_override) < 0.5
            
            if model_correct and followed:
                key = "Model Correct + Followed Model"
            elif model_correct and not followed:
                key = "Model Correct + Overridden"
            elif not model_correct and followed:
                key = "Model Wrong + Followed Model"
            else:
                # Model wrong but override was helpful (bid closer to actual than model)
                override_closer = abs(o.actual_bid - o.model_actual) < abs(o.model_max_bid - o.model_actual)
                if override_closer:
                    key = "Model Wrong + Overridden Successfully"
                else:
                    key = "Model Wrong + Followed Model"  # fallback
            
            entry = {
                "team": team.team_name,
                "property": o.property_id,
                "bid": o.actual_bid,
                "actual": o.model_actual,
                "pred": o.model_pred,
                "value": o.model_actual - o.actual_bid,
            }
            if entry["value"] > 0:
                cases[key].append(entry)
    
    # Display each quadrant
    styles = {
        "Model Correct + Followed Model": "correct-followed",
        "Model Correct + Overridden": "correct-overridden",
        "Model Wrong + Followed Model": "wrong-followed",
        "Model Wrong + Overridden Successfully": "wrong-override-success",
    }
    
    for key, entries in cases.items():
        cls = styles[key]
        st.markdown(f'<div class="matrix-cell {cls}">', unsafe_allow_html=True)
        st.markdown(f'<h5>{key}</h5>')
        if entries:
            for e in entries[:3]:  # Show top 3
                st.markdown(
                    f"- {e['team']} on {e['property']}: "
                    f"bid {fmt_currency(e['bid'])}, actual {fmt_currency(e['actual'])}, "
                    f"{'+' if e['value'] >= 0 else ''}{fmt_delta(e['value'])}"
                )
            if len(entries) > 3:
                st.caption(f"+{len(entries) - 3} more")
        else:
            st.caption("None")
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)


def _show_team_detail(gm, team):
    """Show detailed analysis for one team."""
    overrides = getattr(team, "override_history", [])
    
    st.markdown("**Overrides**")
    if overrides:
        rows = []
        for o in overrides:
            value = o.model_actual - o.actual_bid
            rows.append({
                "Property": o.property_id,
                "Round": o.round_number + 1,
                "Model Max": f"${o.model_max_bid:.2f}M",
                "Your Bid": f"${o.actual_bid:.2f}M",
                "Actual": f"${o.model_actual:.2f}M",
                "Value Created": fmt_delta(value),
                "Action": _interpret_override(o.bid_override),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No overrides — fully followed model")
    
    st.markdown("**Portfolio**")
    if team.properties:
        pf_rows = []
        for pid, h in team.properties.items():
            pf_rows.append({
                "Property": pid,
                "Purchase": f"${h.purchase_price:.2f}M",
                "Current Value": f"${h.current_value:.2f}M",
                "Type": h.property_type,
                "Submarket": h.submarket,
            })
        st.dataframe(pd.DataFrame(pf_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No properties acquired")
    
    st.markdown("**Summary**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Final NAV", f"${team.nav:.2f}M")
    with c2:
        st.metric("Cumulative Return", f"{team.cumulative_return:.1%}")
    with c3:
        st.metric("Properties", len(team.properties))


def _show_strategy_evolution(reflections):
    """Show round-by-round strategy changes."""
    if not reflections:
        st.caption("No round reflections recorded.")
        return
    
    st.markdown(
        """<div style="background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px;padding:1rem;">"""
    )
    for round_num, reflection in reflections.items():
        label = "Practice" if round_num == 0 else f"Round {round_num + 1}"
        st.markdown(f'<div class="strategy-row">', unsafe_allow_html=True)
        st.markdown(f'<span class="strategy-round">{label}:</span>')
        st.markdown(f'<span class="strategy-change">{reflection}</span>')
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _show_professor_view(gm, leaderboard):
    """Professor-level comparison view."""
    if not st.checkbox("Show professor comparison", key="prof_view"):
        return
    
    # NAV by round
    st.markdown("**NAV by Round**")
    nav_rows = []
    for team_id, team in gm.teams.items():
        row = {"Fund": team.team_name}
        nav = 100.0
        row["Pre-Game"] = "$100.00M"
        for rnum in sorted(gm.round_history.keys()):
            if hasattr(team, "round_history") and rnum in team.round_history:
                round_nav = team.round_history[rnum]
                row[f"R{rnum + 1}"] = f"${round_nav:.2f}M"
                nav = round_nav
            else:
                row[f"R{rnum + 1}"] = f"${nav:.2f}M"
        nav_rows.append(row)
    
    if nav_rows:
        st.dataframe(pd.DataFrame(nav_rows), use_container_width=True, hide_index=True)
    
    # Model quality + behavior
    st.markdown("**Model Quality & Behavior**")
    mae_rows = []
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        if overrides:
            errors = [abs(o.model_actual - o.model_pred) for o in overrides if o.model_pred != 0]
            avg_mae = sum(errors) / len(errors) if errors else 0
            avg_ov = sum(o.bid_override for o in overrides) / len(overrides)
            avg_lt = sum(o.ltv for o in overrides) / len(overrides)
            bad_ov = sum(1 for o in overrides if o.bid_override > 1.0 and o.model_actual < o.model_max_bid)
            wins = sum(1 for o in overrides if o.model_actual >= o.actual_bid * 0.98)
            mae_rows.append({
                "Fund": team.team_name,
                "MAE": f"${avg_mae:.2f}M",
                "Overrides": len(overrides),
                "Avg Override": f"${avg_ov:.2f}M",
                "Avg LTV": f"{avg_lt:.0%}",
                "Wins": wins,
                "Bad Overrides": bad_ov,
            })
    
    if mae_rows:
        st.dataframe(pd.DataFrame(mae_rows), use_container_width=True, hide_index=True)
    
    # Discussion prompts
    st.markdown("**Discussion Prompts**")
    prompts = []
    
    # Best model by MAE
    best_model_team = None
    best_model_mae = float("inf")
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        if overrides:
            errors = [abs(o.model_actual - o.model_pred) for o in overrides if o.model_pred != 0]
            avg = sum(errors) / len(errors) if errors else float("inf")
            if avg < best_model_mae:
                best_model_mae = avg
                best_model_team = team
    
    if best_model_team:
        winner_name = leaderboard[0]["team_name"] if leaderboard else None
        if best_model_team.team_name != winner_name:
            prompts.append(
                f"**Which team had the best model but did not win?** "
                f"{best_model_team.team_name} (MAE: ${best_model_mae:.2f}M) vs {winner_name}"
            )
    
    # Best overrides
    best_override_value = 0
    best_override_team = None
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        for o in overrides:
            if o.bid_override > 0 and o.model_actual > o.model_max_bid:
                value = o.model_actual - o.model_max_bid
                if value > best_override_value:
                    best_override_value = value
                    best_override_team = team
    
    if best_override_team:
        prompts.append(
            f"**Which team generated the most value through human overrides?** "
            f"{best_override_team.team_name}"
        )
    
    # Most overpaid
    worst_overpay = 0
    worst_overpay_team = None
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        for o in overrides:
            overpay = max(0, o.actual_bid - o.model_actual)
            if overpay > worst_overpay:
                worst_overpay = overpay
                worst_overpay_team = team
    
    if worst_overpay_team:
        prompts.append(
            f"**Which team overpaid most often?** "
            f"{worst_overpay_team.team_name} (worst single: ${worst_overpay:.2f}M)"
        )
    
    for p in prompts:
        st.caption(p)
    
    # Team detail buttons
    st.markdown("**Team Detail**")
    for team_id, team in gm.teams.items():
        if st.button(f"{team.team_name}", key=f"detail_{team_id}"):
            st.session_state[f"detail_{team_id}"] = True
        if st.session_state.get(f"detail_{team_id}"):
            _show_team_detail(gm, team)
            st.button("Hide", key=f"hide_{team_id}")


# ── MAIN SHOW FUNCTION ──

def show():
    """Display the final debrief."""
    st.markdown(DEBRIEF_CSS, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="page-header">
        <h1>Final Debrief</h1>
        <p>Model quality, decision quality, and realized outcomes</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get game manager
    gm = None
    if "game_manager" in st.session_state:
        gm = st.session_state.game_manager
    else:
        state = st.session_state.get("app_state")
        if state:
            gm = getattr(state, "game_manager", None)
    
    if not gm:
        st.error("No active game. Run the simulation first.")
        return
    
    if not getattr(gm, "game_complete", False):
        st.warning("Game is not complete yet. Wait for all rounds to finish.")
        return
    
    # ── 1. GAME RESULT ──
    st.markdown("<div class='section-header'>Game Result</div>", unsafe_allow_html=True)
    
    leaderboard = gm.get_leaderboard()
    if leaderboard:
        df = pd.DataFrame(leaderboard)
        df = df.sort_values("nav", ascending=False).reset_index(drop=True)
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        winner = leaderboard[0]
        st.caption(
            f"**Winner: {winner['team_name']}** — "
            f"${winner['nav']:.2f}M NAV ({winner['cumulative_return']:.1%} return)"
        )
    
    # ── 2. MODEL VS MANAGER MATRIX ──
    st.markdown("<div class='section-header'>Model vs Manager Matrix</div>", unsafe_allow_html=True)
    st.caption(
        "Classifies every acquisition: was the model right, and did the team follow it?"
    )
    _show_model_matrix(gm, leaderboard)
    
    # ── 3. MODEL QUALITY ──
    st.markdown("<div class='section-header'>Model Quality</div>", unsafe_allow_html=True)
    st.caption("Fair-value MAE across all team acquisitions")
    
    c1, c2, c3, c4 = st.columns(4)
    for i, (tid, team) in enumerate(gm.teams.items()):
        overrides = getattr(team, "override_history", [])
        if overrides:
            errors = [abs(o.model_actual - o.model_pred) for o in overrides if o.model_pred != 0]
            if errors:
                team_mae = sum(errors) / len(errors)
                with [c1, c2, c3, c4][i % 4]:
                    st.metric(team.team_name, f"${team_mae:.2f}M")
    
    # ── 4. MANAGER BEHAVIOR ──
    st.markdown("<div class='section-header'>Manager Behavior</div>", unsafe_allow_html=True)
    
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        with st.expander(f"{team.team_name}", expanded=False):
            if not overrides:
                st.caption("No overrides — fully followed model")
                continue
            
            total_override = sum(o.bid_override for o in overrides)
            avg_override = total_override / len(overrides) if overrides else 0
            avg_ltv = sum(o.ltv for o in overrides) / len(overrides) if overrides else 0
            good_overrides = sum(
                1 for o in overrides
                if (o.bid_override > 0 and o.model_actual > o.model_max_bid)
                or (o.bid_override < 0 and o.model_actual < o.model_max_bid)
            )
            
            st.markdown(f'<div class="data-row"><span class="data-label">Total Overrides</span>'
                        f'<span class="data-value">{len(overrides)}</span></div>',
                        unsafe_allow_html=True)
            
            cls = "positive" if avg_override > 0 else "negative"
            st.markdown(f'<div class="data-row"><span class="data-label">Avg Override</span>'
                        f'<span class="data-value {cls}">{fmt_delta(avg_override)}</span></div>',
                        unsafe_allow_html=True)
            
            st.markdown(f'<div class="data-row"><span class="data-label">Avg LTV Used</span>'
                        f'<span class="data-value">{fmt_pct(avg_ltv)}</span></div>',
                        unsafe_allow_html=True)
            
            st.markdown(f'<div class="data-row"><span class="data-label">Helpful Overrides</span>'
                        f'<span class="data-value positive">{good_overrides}/{len(overrides)}</span></div>',
                        unsafe_allow_html=True)
    
    # ── 5. BEST DECISION ──
    st.markdown("<div class='section-header'>Best Decision</div>", unsafe_allow_html=True)
    _find_best_and_worst(gm)
    
    # ── 6. MOST EXPENSIVE MISTAKE ──
    st.markdown("<div class='section-header'>Most Expensive Mistake</div>", unsafe_allow_html=True)
    # (Already handled in _find_best_and_worst)
    
    # ── 7. LUCK ──
    st.markdown("<div class='section-header'>Luck</div>", unsafe_allow_html=True)
    st.caption("Cases where ex-ante decision quality diverged from realized outcome.")
    
    for team_id, team in gm.teams.items():
        overrides = getattr(team, "override_history", [])
        luck_cases = []
        for o in overrides:
            if o.bid_override < 0.5 and o.model_actual < o.actual_bid * 0.95:
                luck_cases.append((o, "sound_decision_bad_outcome"))
            elif o.bid_override > 1.0 and o.model_actual > o.actual_bid * 1.02:
                luck_cases.append((o, "poor_decision_lucky_outcome"))
        
        if luck_cases:
            with st.expander(f"{team.team_name}"):
                for o, lt in luck_cases:
                    if lt == "sound_decision_bad_outcome":
                        st.markdown(
                            f'<div class="interpretation">'
                            f'Sound decision, bad outcome: {o.property_id} — '
                            f'team bid near model max ({fmt_currency(o.actual_bid)}), '
                            f'but market fell to {fmt_currency(o.model_actual)}'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f'<div class="interpretation">'
                            f'Lucky outcome: {o.property_id} — '
                            f'team overpaid by {fmt_delta(o.bid_override)}, '
                            f'but market rose to {fmt_currency(o.model_actual)}'
                            f'</div>',
                            unsafe_allow_html=True
                        )
    
    # ── 8. STRATEGY EVOLUTION ──
    st.markdown("<div class='section-header'>Strategy Evolution</div>", unsafe_allow_html=True)
    reflections = st.session_state.get("round_reflection", {})
    _show_strategy_evolution(reflections)
    
    # ── PROFESSOR VIEW ──
    st.markdown("<div class='section-header'>Professor View</div>", unsafe_allow_html=True)
    _show_professor_view(gm, leaderboard)
    
    st.markdown("---")
    if st.button("Back to Game", use_container_width=True):
        st.switch_page("app.py")
