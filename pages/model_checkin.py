"""
Model Check-In page for uploading prediction submissions.

Teams upload their model predictions before the game starts.
The page validates the submission and stores it for use during gameplay.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

from src.models.submission import validate_submission, REQUIRED_COLUMNS, OPTIONAL_COLUMNS
from src.utils.state import AppState


def show():
    """Display the model check-in page."""
    st.title("Model Check-In")
    st.caption("Upload your team's prediction submissions before the game begins")
    
    state = st.session_state.get("app_state")
    if not state:
        st.error("Application state not initialized. Please restart the demo.")
        return
    
    # Instructions
    with st.expander("How to prepare your submission", expanded=True):
        st.markdown("""
        ### Before uploading:
        
        1. Download the prediction template from the student packet
        2. Build your model using Excel, Python, R, or any tool you prefer
        3. Generate predictions for all game candidate properties
        4. Fill in the required columns:
           - `property_id` - Must match game candidates exactly
           - `predicted_fair_value` - Your model's valuation (in millions)
           - `predicted_noi` - Predicted NOI (in millions)
           - `predicted_noi_growth` - Expected annual NOI growth (decimal, e.g., 0.03 for 3%)
           - `max_bid` - Maximum price your model recommends (in millions)
           - `target_ltv` - Recommended loan-to-value ratio (decimal, e.g., 0.60 for 60%)
           - `model_name` - Name of your model
           - `model_version` - Version identifier
        
        5. Optional columns:
           - `probability_of_downside` - Probability of negative outcome (0-1)
           - `confidence` - Your confidence in the prediction (0-1)
           - `predicted_exit_cap` - Predicted exit cap rate
           - `notes` - Any additional context
        
        6. Save as CSV and upload below
        
        ### Important:
        - The game will display YOUR predictions during gameplay
        - Other teams cannot see your predictions
        - The game does NOT validate whether your predictions are accurate
        - Accuracy is revealed only after rounds resolve
        """)
    
    # File upload
    st.markdown("---")
    st.subheader("Upload Your Predictions")
    
    uploaded_file = st.file_uploader(
        "Upload your prediction CSV",
        type=["csv"],
        help="Select the CSV file containing your model predictions"
    )
    
    if uploaded_file:
        try:
            # Read the uploaded file
            df = pd.read_csv(uploaded_file)
            
            st.success(f"File uploaded successfully: {uploaded_file.name}")
            st.write(f"Found {len(df)} property predictions")
            
            # Show preview
            with st.expander("Preview your submission", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Validate submission
            st.subheader("Validation")
            validation_result = validate_submission(df)
            
            if validation_result["ok"]:
                st.success("✅ Submission is valid!")
                
                # Show validation statistics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Properties", len(df))
                with col2:
                    st.metric("Avg Predicted Value", f"${df['predicted_value'].mean():.2f}M")
                with col3:
                    st.metric("Avg Max Bid", f"${df['max_bid'].mean():.2f}M")
                with col4:
                    st.metric("Avg Target LTV", f"{df['target_ltv'].mean():.1%}")
                
                # Show strategy summary
                st.subheader("Strategy Summary")
                with st.expander("View your model's strategy"):
                    # Top opportunities (largest discount to fair value)
                    df["discount_to_ask"] = None  # Will calculate when game candidates are loaded
                    df["bid_discipline"] = df["max_bid"] / df["predicted_fair_value"]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Most Aggressive Bids** (highest bid discipline)")
                        aggressive = df.nlargest(5, "bid_discipline")[["property_id", "predicted_fair_value", "max_bid", "bid_discipline"]]
                        st.dataframe(aggressive, use_container_width=True)
                    
                    with col2:
                        st.write("**Most Conservative Bids** (lowest bid discipline)")
                        conservative = df.nsmallest(5, "bid_discipline")[["property_id", "predicted_fair_value", "max_bid", "bid_discipline"]]
                        st.dataframe(conservative, use_container_width=True)
                    
                    st.write("**Downside Risk Distribution**")
                    if "probability_of_downside" in df.columns:
                        st.bar_chart(df["probability_of_downside"].hist(bins=10))
                    else:
                        st.info("No downside probabilities provided")
                
                # Confirm submission
                st.markdown("---")
                st.subheader("Confirm Submission")
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    team_name = st.text_input("Team Name", value="Team 1", help="Enter your team name")
                with col2:
                    model_summary = st.text_area("Brief Model Description", placeholder="e.g., XGBoost with 50 features including submarket vacancy and employment growth")
                
                if st.button("Submit Predictions", type="primary", use_container_width=True):
                    # Store in session state
                    if not hasattr(state, "team_predictions"):
                        state.team_predictions = {}
                    
                    state.team_predictions[team_name] = {
                        "data": df,
                        "model_name": df["model_name"].iloc[0] if "model_name" in df.columns else "Unknown",
                        "model_version": df["model_version"].iloc[0] if "model_version" in df.columns else "1.0",
                        "submitted_at": pd.Timestamp.now().isoformat(),
                        "team_name": team_name,
                        "model_summary": model_summary,
                    }
                    
                    state.log(f"Team {team_name} submitted predictions with {len(df)} properties")
                    st.success(f"✅ Predictions submitted for {team_name}!")
                    st.balloons()
                    st.info("You can now proceed to the Strategy Card or wait for the game to begin.")
                    
            else:
                st.error("❌ Submission has errors")
                for error in validation_result["errors"]:
                    st.error(f"• {error}")
                
                if validation_result["warnings"]:
                    st.warning("Warnings:")
                    for warning in validation_result["warnings"]:
                        st.warning(f"• {warning}")
        
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
            st.info("Please ensure your file is a valid CSV with the correct format.")
    
    # Show existing submissions (if any)
    if hasattr(state, "team_predictions") and state.team_predictions:
        st.markdown("---")
        st.subheader("Submitted Teams")
        
        for team_name, submission in state.team_predictions.items():
            with st.expander(f"{team_name} - {submission['model_name']} v{submission['model_version']}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Properties", len(submission["data"]))
                col2.metric("Submitted", submission["submitted_at"][:19])
                col3.metric("Model", submission["model_name"])
                
                if submission.get("model_summary"):
                    st.write(f"**Description:** {submission['model_summary']}")
    
    # Download template link
    st.markdown("---")
    st.subheader("Resources")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Download Prediction Template"):
            # Generate template
            template = pd.DataFrame(columns=REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
            csv = template.to_csv(index=False)
            st.download_button(
                label="Download CSV Template",
                data=csv,
                file_name="prediction_submission_template.csv",
                mime="text/csv"
            )
    
    with col2:
        st.info("📁 Student packet files should be available from your instructor or in the `student_packet/` directory.")
