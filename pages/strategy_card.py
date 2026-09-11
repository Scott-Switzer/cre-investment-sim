"""
Strategy Card page showing team's own model outputs.

After uploading predictions, this page displays a summary of the team's
model-derived strategy without revealing whether the model is accurate.
"""

import streamlit as st
import pandas as pd
import numpy as np

from src.utils.state import AppState


def show():
    """Display the strategy card page."""
    st.title("Strategy Card")
    st.caption("Review your model's strategy before the game begins")
    
    state = st.session_state.get("app_state")
    if not state:
        st.error("Application state not initialized. Please restart the demo.")
        return
    
    # Check if team has submitted predictions
    if not hasattr(state, "team_predictions") or not state.team_predictions:
        st.warning("No predictions submitted yet. Please go to Model Check-In to upload your predictions.")
        st.info("Once you upload your predictions, this page will show your model's strategy summary.")
        return
    
    # Select team (for demo mode, default to first team)
    team_names = list(state.team_predictions.keys())
    if len(team_names) == 1:
        team_name = team_names[0]
    else:
        team_name = st.selectbox("Select Team", team_names)
    
    submission = state.team_predictions[team_name]
    df = submission["data"].copy()
    
    st.header(f"{team_name}")
    st.caption(f"Model: {submission['model_name']} v{submission['model_version']}")
    
    # Calculate strategy metrics
    df["bid_discipline"] = df["max_bid"] / df["predicted_fair_value"]
    df["value_to_ask_ratio"] = df["predicted_fair_value"] / df["predicted_fair_value"]  # Placeholder - needs asking prices
    
    # Strategy overview
    st.markdown("---")
    st.subheader("Model Strategy Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Properties", len(df))
    with col2:
        avg_discipline = df["bid_discipline"].mean()
        st.metric("Avg Bid Discipline", f"{avg_discipline:.1%}")
    with col3:
        avg_ltv = df["target_ltv"].mean()
        st.metric("Avg Target LTV", f"{avg_ltv:.1%}")
    with col4:
        if "probability_of_downside" in df.columns:
            avg_risk = df["probability_of_downside"].mean()
            st.metric("Avg Downside Risk", f"{avg_risk:.1%}")
        else:
            st.metric("Avg Downside Risk", "N/A")
    
    # Pre-game policy settings
    st.markdown("---")
    st.subheader("Pre-Game Policy Settings")
    
    st.info("""
    Set your investment policy constraints before the game starts.
    These settings will help you stay disciplined during timed rounds.
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        min_discount = st.number_input(
            "Minimum Required Discount to Fair Value",
            min_value=0.0,
            max_value=0.5,
            value=0.0,
            step=0.01,
            format="%.0%",
            help="Only bid if asking price is at least this much below your predicted fair value"
        )
        max_ltv_policy = st.number_input(
            "Maximum LTV",
            min_value=0.0,
            max_value=0.95,
            value=0.75,
            step=0.05,
            format="%.0%",
            help="Never exceed this LTV regardless of model recommendation"
        )
    
    with col2:
        max_equity_per_property = st.number_input(
            "Maximum Equity per Property",
            min_value=0.0,
            max_value=100.0,
            value=25.0,
            step=5.0,
            help="Maximum equity to invest in a single property (in millions)"
        )
        max_properties_per_round = st.number_input(
            "Maximum Properties per Round",
            min_value=1,
            max_value=4,
            value=2,
            step=1,
            help="Maximum number of properties to acquire in a single round"
        )
    
    # Store policy in session state
    if not hasattr(state, "team_policies"):
        state.team_policies = {}
    
    state.team_policies[team_name] = {
        "min_discount": min_discount,
        "max_ltv": max_ltv_policy,
        "max_equity_per_property": max_equity_per_property,
        "max_properties_per_round": max_properties_per_round,
    }
    
    # Top opportunities
    st.markdown("---")
    st.subheader("Top Model Opportunities")
    
    with st.expander("Properties with Highest Predicted Value", expanded=True):
        top_value = df.nlargest(10, "predicted_fair_value")[
            ["property_id", "predicted_fair_value", "predicted_noi_growth", "max_bid", "target_ltv"]
        ]
        st.dataframe(top_value, use_container_width=True)
    
    with st.expander("Most Conservative Bids (Highest Discipline)"):
        conservative = df.nsmallest(10, "bid_discipline")[
            ["property_id", "predicted_fair_value", "max_bid", "bid_discipline", "target_ltv"]
        ]
        st.dataframe(conservative, use_container_width=True)
    
    with st.expander("Most Aggressive Bids (Lowest Discipline)"):
        aggressive = df.nlargest(10, "bid_discipline")[
            ["property_id", "predicted_fair_value", "max_bid", "bid_discipline", "target_ltv"]
        ]
        st.dataframe(aggressive, use_container_width=True)
    
    # Risk analysis
    if "probability_of_downside" in df.columns:
        st.markdown("---")
        st.subheader("Risk Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**High-Risk Properties** (downside probability > 50%)")
            high_risk = df[df["probability_of_downside"] > 0.5].sort_values("probability_of_downside", ascending=False)[
                ["property_id", "predicted_fair_value", "probability_of_downside", "max_bid"]
            ]
            if len(high_risk) > 0:
                st.dataframe(high_risk.head(10), use_container_width=True)
            else:
                st.info("No high-risk properties identified")
        
        with col2:
            st.write("**Low-Risk Properties** (downside probability < 20%)")
            low_risk = df[df["probability_of_downside"] < 0.2].sort_values("probability_of_downside")[
                ["property_id", "predicted_fair_value", "probability_of_downside", "max_bid"]
            ]
            if len(low_risk) > 0:
                st.dataframe(low_risk.head(10), use_container_width=True)
            else:
                st.info("No low-risk properties identified")
        
        # Risk distribution chart
        st.write("**Downside Risk Distribution**")
        st.bar_chart(df["probability_of_downside"].hist(bins=20))
    
    # NOI growth analysis
    st.markdown("---")
    st.subheader("NOI Growth Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Highest Expected NOI Growth**")
        high_growth = df.nlargest(10, "predicted_noi_growth")[
            ["property_id", "predicted_noi_growth", "predicted_fair_value", "max_bid"]
        ]
        st.dataframe(high_growth, use_container_width=True)
    
    with col2:
        st.write("**Lowest/Declining NOI Growth**")
        low_growth = df.nsmallest(10, "predicted_noi_growth")[
            ["property_id", "predicted_noi_growth", "predicted_fair_value", "max_bid"]
        ]
        st.dataframe(low_growth, use_container_width=True)
    
    # Leverage analysis
    st.markdown("---")
    st.subheader("Leverage Analysis")
    
    st.write("**Target LTV Distribution**")
    st.bar_chart(df["target_ltv"].hist(bins=20))
    
    with st.expander("High-LTV Recommendations"):
        high_ltv = df[df["target_ltv"] > 0.70].sort_values("target_ltv", ascending=False)[
            ["property_id", "target_ltv", "predicted_fair_value", "max_bid"]
        ]
        st.dataframe(high_ltv, use_container_width=True)
    
    with st.expander("Low-LTV Recommendations"):
        low_ltv = df[df["target_ltv"] < 0.50].sort_values("target_ltv")[
            ["property_id", "target_ltv", "predicted_fair_value", "max_bid"]
        ]
        st.dataframe(low_ltv, use_container_width=True)
    
    # Properties to avoid
    st.markdown("---")
    st.subheader("Properties Your Model Says to Avoid")
    
    # Identify properties where model says max_bid is very low relative to fair value
    # or downside risk is very high
    avoid_reasons = []
    for _, row in df.iterrows():
        reasons = []
        if row["bid_discipline"] < 0.8:
            reasons.append("Very conservative bid discipline")
        if "probability_of_downside" in df.columns and row["probability_of_downside"] > 0.6:
            reasons.append("High downside risk")
        if row["predicted_noi_growth"] < -0.05:
            reasons.append("Negative NOI growth expected")
        
        if reasons:
            avoid_reasons.append({
                "property_id": row["property_id"],
                "predicted_fair_value": row["predicted_fair_value"],
                "reasons": ", ".join(reasons),
            })
    
    if avoid_reasons:
        avoid_df = pd.DataFrame(avoid_reasons)
        st.dataframe(avoid_df, use_container_width=True)
    else:
        st.info("Your model does not flag any properties as strong avoids")
    
    # Ready to play
    st.markdown("---")
    st.subheader("Ready to Play")
    
    st.success(f"""
    ✅ Your strategy card is ready for {team_name}!
    
    **Your Policy:**
    - Minimum discount to fair value: {min_discount:.0%}
    - Maximum LTV: {max_ltv_policy:.0%}
    - Maximum equity per property: ${max_equity_per_property:.0f}M
    - Maximum properties per round: {max_properties_per_round}
    
    During the game, refer to this strategy to stay disciplined.
    Remember: your model's predictions will appear beside each property during gameplay.
    """)
    
    if st.button("Proceed to Live Game", type="primary", use_container_width=True):
        st.info("Navigate to the Live Game section when the instructor starts the game.")
