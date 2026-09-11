"""
REAL 605 CRE Investment Committee Simulation — Game UI
"""
from __future__ import annotations

import streamlit as st
import time
from datetime import date
import pages
from src.utils.state import AppState, build_demo_state
from src.utils.config import load_app_config
from src.simulation.engine import SCENARIOS
from src.game.manager import GameManager, GameConfig
from src.game.adjudicator import RoundState, Bid, ModelPrediction

# ─── GLOBAL GAME STYLES ────────────────────────────────────────────────
GAME_CSS = """
<style>
/* Game-style theme */
:root {
    --game-bg: #0a0e17;
    --game-card: #111827;
    --game-border: #1e293b;
    --game-accent: #3b82f6;
    --game-success: #10b981;
    --game-warning: #f59e0b;
    --game-danger: #ef4444;
    --game-text: #f1f5f9;
    --game-muted: #94a3b8;
}

/* Override Streamlit defaults */
.stApp {
    background: var(--game-bg);
    color: var(--game-text);
}

.stApp > header,
.stApp > footer {
    background: var(--game-card) !important;
    border-bottom: 1px solid var(--game-border);
}

/* Game header */
.game-header {
    text-align: center;
    padding: 20px 0;
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    border-radius: 12px;
    margin-bottom: 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}

.game-header h1 {
    color: white;
    margin: 0;
    font-size: 2.5em;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
}

.game-header h2 {
    color: #dbeafe;
    margin: 10px 0 0 0;
    font-size: 1.2em;
    font-weight: 300;
}

/* Round badge */
.round-badge {
    display: inline-block;
    background: var(--game-accent);
    color: white;
    padding: 8px 24px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 1.1em;
    margin: 10px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
}

/* Game cards */
.game-card {
    background: var(--game-card);
    border: 1px solid var(--game-border);
    border-radius: 8px;
    padding: 16px;
    margin: 10px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

/* Stats grid */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    margin: 20px 0;
}

.stat-item {
    background: var(--game-card);
    border: 1px solid var(--game-border);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
}

.stat-value {
    font-size: 1.5em;
    font-weight: bold;
    color: var(--game-accent);
}

.stat-label {
    font-size: 0.9em;
    color: var(--game-muted);
    margin-top: 4px;
}

/* Property cards */
.property-card {
    background: var(--game-card);
    border: 2px solid var(--game-border);
    border-radius: 12px;
    padding: 20px;
    margin: 15px 0;
    transition: all 0.3s ease;
}

.property-card:hover {
    border-color: var(--game-accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59,130,246,0.3);
}

.property-card.possible-buy {
    border-color: var(--game-success);
}

.property-card.overpriced {
    border-color: var(--game-danger);
}

/* Buttons */
.stButton > button {
    background: var(--game-accent) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 12px 24px !important;
    font-weight: bold !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

.stButton > button:hover {
    background: #2563eb !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59,130,246,0.4);
}

.stButton > button[data-testid="stBaseButton-secondary"] {
    background: var(--game-muted) !important;
}

/* Tables */
.stDataFrame {
    background: var(--game-card);
    border-radius: 8px;
    border: 1px solid var(--game-border);
}

/* Metrics */
.stMetric {
    background: var(--game-card);
    border-radius: 8px;
    padding: 12px;
    border: 1px solid var(--game-border);
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--game-card) !important;
}

[data-testid="stSidebar"] .stButton > button {
    width: 100% !important;
}

/* Progress bars */
.stProgress > div > div {
    background: var(--game-accent) !important;
}

/* Custom components */
.bronze-medal { color: #cd7f32; }
.silver-medal { color: #c0c0c0; }
.gold-medal { color: #ffd700; }

/* Animations */
@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.pulse {
    animation: pulse 2s infinite;
}

/* Leaderboard styling */
.leaderboard-entry {
    background: var(--game-card);
    border: 1px solid var(--game-border);
    border-radius: 8px;
    padding: 15px;
    margin: 10px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.leaderboard-entry.rank-1 {
    border-color: #ffd700;
    background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
}

.leaderboard-entry.rank-2 {
    border-color: #c0c0c0;
}

.leaderboard-entry.rank-3 {
    border-color: #cd7f32;
}

/* Debrief sections */
.debrief-section {
    background: var(--game-card);
    border-left: 4px solid var(--game-accent);
    padding: 20px;
    margin: 20px 0;
    border-radius: 0 8px 8px 0;
}

/* Game log */
.game-log {
    background: #0f172a;
    border: 1px solid var(--game-border);
    border-radius: 8px;
    padding: 15px;
    font-family: monospace;
    font-size: 0.9em;
    max-height: 300px;
    overflow-y: auto;
}

.game-log-entry {
    padding: 5px 0;
    border-bottom: 1px solid var(--game-border);
}

.game-log-entry:last-child {
    border-bottom: none;
}

/* Loading animation */
.loading-spinner {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 40px;
}

.loading-spinner::before {
    content: '';
    width: 40px;
    height: 40px;
    border: 4px solid var(--game-border);
    border-top: 4px solid var(--game-accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>
"""

# ─── APP CONFIG ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CRE Investment Game",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(GAME_CSS, unsafe_allow_html=True)

APP_CFG = load_app_config()
DECISION_DATE = date.fromisoformat(APP_CFG.get("app", {}).get("decision_date", "2024-03-31"))
AVAILABLE_CAPITAL = APP_CFG.get("app", {}).get("available_capital_mm", 150.0)

# ─── SESSION STATE MANAGEMENT ─────────────────────────────────────────
if "game_manager" not in st.session_state:
    st.session_state.game_manager = None
if "current_team" not in st.session_state:
    st.session_state.current_team = None
if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "game_complete" not in st.session_state:
    st.session_state.game_complete = False
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = True  # Default to demo mode
if "game_log" not in st.session_state:
    st.session_state.game_log = []

# ─── UTILITY FUNCTIONS ────────────────────────────────────────────────
def add_game_log(message: str, level: str = "info"):
    """Add entry to game log."""
    st.session_state.game_log.append({
        "message": message,
        "level": level,
        "time": time.strftime("%H:%M:%S")
    })
    # Keep only last 100 entries
    if len(st.session_state.game_log) > 100:
        st.session_state.game_log = st.session_state.game_log[-100:]

def create_game_teams() -> GameManager:
    """Create game with 3 bot competitors."""
    config = GameConfig(
        seed=20240331,
        starting_equity=100.0,
        total_rounds=4,
        properties_per_round=4,
        practice_round=True,
        scenario="Base Case",
    )
    gm = GameManager(config)
    
    # Add human player
    gm.add_team("Buy&Hold Capital", "Buy&Hold Capital")
    
    # Add demo teams (bots)
    from scripts.create_demo_teams import create_demo_teams
    demo_preds = create_demo_teams(seed=20240331, count=120)
    
    bot_names = ["Value Fund", "Growth Fund", "Risk Fund"]
    for i, (bot_name, pred_df) in enumerate(demo_preds.items()):
        if i >= 3:
            break
        mp = {}
        for _, row in pred_df.iterrows():
            mp[str(row["property_id"])] = ModelPrediction(
                property_id=str(row["property_id"]),
                predicted_fair_value=float(row["predicted_fair_value"]),
                predicted_noi_growth=float(row["predicted_noi_growth"]),
                probability_of_downside=float(row["probability_of_downside"]),
                max_bid=float(row["max_bid"]),
                target_ltv=float(row["target_ltv"]),
                model_name=bot_name + " Model",
                confidence=float(row["confidence"]),
                predicted_exit_cap=float(row["predicted_exit_cap"]),
            )
        gm.add_team(bot_name, bot_name, mp)
    
    return gm

def show_game_header(title: str, subtitle: str = ""):
    """Display game-style header."""
    st.markdown(f'''
    <div class="game-header">
        <h1>🏢 {title}</h1>
        {f'<h2>{subtitle}</h2>' if subtitle else ''}
    </div>
    ''', unsafe_allow_html=True)

def show_stats_grid(stats: dict):
    """Display stats in a grid."""
    cols = st.columns(len(stats))
    for i, (label, value) in enumerate(stats.items()):
        with cols[i]:
            st.markdown(f'''
            <div class="stat-item">
                <div class="stat-value">{value}</div>
                <div class="stat-label">{label}</div>
            </div>
            ''', unsafe_allow_html=True)

# ─── MAIN APP LOGIC ──────────────────────────────────────────────────
# Check if we're in game mode
if st.session_state.game_started and st.session_state.game_manager:
    gm = st.session_state.game_manager
    team_name = st.session_state.current_team or "Buy&Hold Capital"
    team_state = gm.teams.get(team_name)
    
    # Show game header
    show_game_header("CRE Investment Committee", "Real Estate Analytics Simulation")
    
    # Game status bar
    status_cols = st.columns(5)
    with status_cols[0]:
        st.markdown(f'<div class="round-badge">ROUND {gm.current_round + 1 if gm.current_round >= 0 else "PRACTICE"}</div>', unsafe_allow_html=True)
    with status_cols[1]:
        st.metric("Cash", f"${team_state.cash:.1f}M" if team_state else "$100M")
    with status_cols[2]:
        st.metric("NAV", f"${team_state.nav:.1f}M" if team_state else "$100M")
    with status_cols[3]:
        st.metric("Properties", len(team_state.properties) if team_state else 0)
    with status_cols[4]:
        st.metric("Debt", f"${team_state.debt:.1f}M" if team_state else "$0M")
    
    st.markdown("---")
    
    # Game state handling
    if gm.game_complete:
        # Show final results
        st.markdown('<div class="game-header"><h1>🏆 GAME COMPLETE</h1></div>', unsafe_allow_html=True)
        
        # Final standings
        leaderboard = gm.get_leaderboard()
        if leaderboard:
            st.subheader("🏆 Final Standings")
            for i, entry in enumerate(leaderboard[:5]):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
                st.markdown(f'''
                <div class="leaderboard-entry rank-{i+1}">
                    <div>
                        <strong>{medal} {entry["team_name"]}</strong>
                    </div>
                    <div>
                        <strong>${entry["nav"]:.2f}M NAV</strong>
                        <span style="color: #94a3b8"> ({entry["cumulative_return"]:.1%})</span>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            
            # Play again button
            if st.button("🔄 PLAY AGAIN", type="primary", use_container_width=True):
                st.session_state.game_manager = None
                st.session_state.game_started = False
                st.session_state.game_complete = False
                st.session_state.game_log = []
                st.rerun()
        
        # Show game log
        with st.expander("📋 Game Log", expanded=False):
            for entry in st.session_state.game_log[-20:]:
                st.text(f"[{entry['time']}] {entry['message']}")
    
    elif gm.round_state == RoundState.OPEN:
        # Show bidding interface
        st.markdown('<div class="round-badge">⚡ SUBMISSIONS OPEN</div>', unsafe_allow_html=True)
        st.caption("Make your investment decisions below")
        
        # Show current properties
        st.subheader("🏢 Available Properties")
        
        for prop_id, prop in gm.current_properties.items():
            with st.container():
                st.markdown(f'''
                <div class="property-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h3>{prop.property_name}</h3>
                            <p style="color: #94a3b8;">{prop.property_type} · {prop.submarket}</p>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2em; font-weight: bold; color: #3b82f6;">${prop.asking_price:.1f}M</div>
                            <div style="color: #94a3b8;">Cap Rate: {prop.current_cap:.1%}</div>
                        </div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            
            # Decision controls
            col1, col2 = st.columns([1, 2])
            with col1:
                decision = st.radio(
                    "Your Decision",
                    ["PASS", "BID"],
                    key=f"dec_{prop_id}",
                    horizontal=True
                )
            
            if decision == "BID":
                col_bid, col_ltv = st.columns(2)
                with col_bid:
                    bid_price = st.number_input(
                        "Bid Price ($M)",
                        min_value=0.0,
                        max_value=prop.asking_price * 1.2,
                        value=float(prop.asking_price * 0.95),
                        step=0.5,
                        format="%.1f",
                        key=f"bid_{prop_id}"
                    )
                with col_ltv:
                    bid_ltv = st.number_input(
                        "LTV",
                        min_value=0.0,
                        max_value=prop.max_ltv,
                        value=0.60,
                        step=0.05,
                        format="%.2f",
                        key=f"ltv_{prop_id}"
                    )
            
            # Show equity requirement
            if decision == "BID":
                bid_price_val = float(st.session_state.get(f"bid_{prop_id}", prop.asking_price))
                bid_ltv_val = float(st.session_state.get(f"ltv_{prop_id}", 0.6))
                eq_required = bid_price_val * (1 - bid_ltv_val)
                if team_state and eq_required > team_state.cash:
                    st.error(f"❌ Insufficient equity: need ${eq_required:.1f}M, have ${team_state.cash:.1f}M")
                else:
                    st.success(f"✅ Equity required: ${eq_required:.1f}M")
        
        # Submit button
        if st.button("🔒 SUBMIT ALL DECISIONS", type="primary", use_container_width=True):
            submitted = []
            for prop_id in gm.current_properties.keys():
                decision = st.session_state.get(f"dec_{prop_id}", "PASS")
                if decision == "BID":
                    bid = Bid(
                        team_id=team_name,
                        property_id=prop_id,
                        bid_price=float(st.session_state.get(f"bid_{prop_id}", 0)),
                        ltv=float(st.session_state.get(f"ltv_{prop_id}", 0.6)),
                        round_number=gm.current_round,
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        confidence=0.8,
                    )
                    try:
                        gm.submit_bid(bid)
                        submitted.append(prop_id)
                    except ValueError as e:
                        st.error(f"❌ {prop_id}: {e}")
            
            if submitted:
                st.success(f"✅ {len(submitted)} decision(s) locked!")
                add_game_log(f"Submitted {len(submitted)} bids")
                st.rerun()
    
    elif gm.round_state == RoundState.LOCKED:
        # Show locked state
        st.markdown('<div class="game-header"><h1>🔒 ROUNDS LOCKED</h1></div>', unsafe_allow_html=True)
        st.info("Decisions are locked. Waiting for market close...")
        
        # Show submitted bids
        st.subheader("📝 Your Decisions")
        submitted = [b for b in gm.submitted_bids if b.team_id == team_name]
        if submitted:
            for bid in submitted:
                st.markdown(f'''
                <div class="game-card">
                    <strong>{bid.property_id}</strong> · 
                    Bid: <span style="color: #3b82f6;">${bid.bid_price:.1f}M</span> · 
                    LTV: {bid.ltv:.0%}
                </div>
                ''', unsafe_allow_html=True)
        
        # Auto-advance button for demo mode
        if st.session_state.demo_mode:
            if st.button("▶️ RESOLVE ROUND", type="primary", use_container_width=True):
                try:
                    result = gm.resolve_round()
                    st.session_state.last_round_result = result
                    add_game_log(f"Round resolved: {len(result.auction_results)} properties")
                    st.rerun()
                except Exception as e:
                    st.error(f"Resolve failed: {e}")
    
    elif gm.round_state == RoundState.RESOLVED:
        # Show results
        st.markdown('<div class="game-header"><h1>📊 ROUND RESULTS</h1></div>', unsafe_allow_html=True)
        
        result = gm.current_round_result
        if result:
            st.subheader("🏆 Auction Results")
            for prop_id, auction in result.auction_results.items():
                if auction.sold:
                    if auction.winning_team_id == team_name:
                        st.success(f"🎉 You won {prop_id} for ${auction.winning_bid:.1f}M")
                    else:
                        st.info(f"Sold to {auction.winning_team_id} for ${auction.winning_bid:.1f}M")
                else:
                    st.warning(f"Not sold (reserve: ${auction.reserve_price:.1f}M)")
            
            # Portfolio update
            if team_state:
                st.subheader("💼 Your Portfolio")
                if team_state.properties:
                    for prop_id, holding in team_state.properties.items():
                        st.markdown(f'''
                        <div class="game-card">
                            <strong>{prop_id}</strong> · 
                            Purchase: <span style="color: #3b82f6;">${holding.purchase_price:.1f}M</span> · 
                            Current: <span style="color: #10b981;">${holding.current_value:.1f}M</span>
                        </div>
                        ''', unsafe_allow_html=True)
                else:
                    st.info("No properties acquired yet.")
        
        # Continue button
        if st.button("▶️ CONTINUE TO NEXT ROUND", type="primary", use_container_width=True):
            try:
                gm.advance_round()
                add_game_log("Advanced to next round")
                st.rerun()
            except RuntimeError as e:
                st.error(f"Advance failed: {e}")
    
    else:
        # Not started state
        st.markdown('<div class="game-header"><h1>🏢 READY TO PLAY</h1></div>', unsafe_allow_html=True)
        st.info("Click 'Start Practice Round' to begin the simulation.")
        
        if st.button("🚀 START PRACTICE ROUND", type="primary", use_container_width=True):
            gm.start_game()
            st.session_state.game_started = True
            add_game_log("Practice round started")
            st.rerun()

# ─── GAME START SCREEN ───────────────────────────────────────────────
else:
    show_game_header("CRE Investment Committee", "Real Estate Analytics Simulation")
    
    st.markdown('''
    <div class="debrief-section">
        <h3>🎯 Mission</h3>
        <p>Build the best real estate portfolio through 4 rounds of strategic investing. 
        Analyze properties, make bids, and outperform 3 automated fund managers.</p>
        
        <h3>📊 How to Play</h3>
        <ol>
            <li><strong>Practice Round:</strong> Learn the interface (non-scored)</li>
            <li><strong>Rounds 1-4:</strong> Bid on commercial properties</li>
            <li><strong>Winning:</strong> Highest valid bid wins each property</li>
            <li><strong>Scoring:</strong> Final NAV determines your rank</li>
        </ol>
        
        <h3>🤖 Competitors</h3>
        <ul>
            <li><strong>Value Fund:</strong> Disciplined, value-focused bidding</li>
            <li><strong>Growth Fund:</strong> Aggressive, growth-oriented bidding</li>
            <li><strong>Risk Fund:</strong> Conservative, risk-averse bidding</li>
        </ul>
    </div>
    ''', unsafe_allow_html=True)
    
    # Start button
    if st.button("🚀 START SIMULATION", type="primary", use_container_width=True, help="Start the practice round"):
        gm = create_game_teams()
        st.session_state.game_manager = gm
        st.session_state.current_team = "Buy&Hold Capital"
        st.session_state.game_started = True
        add_game_log("Simulation initialized with 3 bot competitors")
        st.rerun()
    
    # Game log (if any)
    if st.session_state.game_log:
        with st.expander("📋 Game Log", expanded=False):
            for entry in st.session_state.game_log[-10:]:
                st.text(f"[{entry['time']}] {entry['message']}")

# ─── SIDEBAR ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎮 Game Controls")
    
    if st.session_state.game_started:
        if st.button("🔄 Reset Game", type="secondary"):
            st.session_state.game_manager = None
            st.session_state.game_started = False
            st.session_state.game_complete = False
            st.session_state.game_log = []
            st.rerun()
        
        if st.button("📊 Leaderboard", use_container_width=True):
            st.switch_page("pages/leaderboard.py")
        
        if st.button("📋 Final Debrief", use_container_width=True):
            st.switch_page("pages/final_debrief.py")
    else:
        st.info("Start a simulation to see game controls")
    
    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.caption("REAL 605 CRE Investment Committee Simulation")
    st.caption("Chapman University · Prof. Tim Frenzel")
