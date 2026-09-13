"""
Model Check-In page.

Teams upload their externally-built model predictions before play. The page
validates the submission against the authoritative game contract
(:mod:`src.game.submission`) and stores the predictions for use during the live
game.

Design constraint: this page reports *structural* validation only. It must never
reveal whether a team's predictions are accurate -- accuracy is revealed only as
rounds resolve.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.game.submission import (
    ALL_COLUMNS,
    REQUIRED_COLUMNS,
    OPTIONAL_COLUMNS,
    validate_game_submission,
)

PACKET_DIR = Path("student_packet")
CANDIDATES_PATH = PACKET_DIR / "game_candidates.csv"
TEMPLATE_PATH = PACKET_DIR / "prediction_submission_template.csv"


def candidate_property_ids() -> list[str]:
    """Property ids the game can actually offer, from the student packet."""
    if not CANDIDATES_PATH.exists():
        return []
    try:
        return [str(p) for p in pd.read_csv(CANDIDATES_PATH)["property_id"].tolist()]
    except Exception:
        return []


def show():
    st.title("Model Check-In")
    st.caption("Upload your team's model outputs before the game begins")

    with st.expander("How to prepare your submission", expanded=False):
        st.markdown(
            f"""
### Before class

1. Download the student packet (dataset downloads page, or `{PACKET_DIR}/`).
2. Build a model externally — Excel, Python, R, anything.
3. Predict every game candidate property.
4. Save as CSV and upload here.

### Required columns

`{"`, `".join(REQUIRED_COLUMNS)}`

### Optional columns

`{"`, `".join(OPTIONAL_COLUMNS)}`

### Units

Money columns are in **millions**. Rates and probabilities are **decimals**
(`0.03` means 3%).

### What happens next

- The game displays **your** predictions beside each deal during play.
- No other team can see them.
- The game does **not** check whether your predictions are accurate.
- Accuracy is revealed only as rounds resolve.
"""
        )

    st.markdown("---")
    st.subheader("Upload Your Predictions")

    uploaded = st.file_uploader("Prediction CSV", type=["csv"])

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001 - surface parse failure to the user
            st.error(f"Could not read file: {exc}")
            return

        st.success(f"Loaded {uploaded.name} — {len(df)} rows")

        valid_ids = candidate_property_ids()
        result = validate_game_submission(df, valid_ids or None)

        st.subheader("Validation")
        if result.ok:
            st.success("Submission is structurally valid.")
        else:
            st.error("Submission has errors:")
            for err in result.errors:
                st.error(f"• {err}")

        for warn in result.warnings:
            st.warning(f"• {warn}")

        if not valid_ids:
            st.info(
                "Game candidate list not found on disk, so property ids could not be "
                "checked against the game. Run `python scripts/build_student_game_packet.py`."
            )

        if result.stats:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows", int(result.stats.get("rows", 0)))
            c2.metric("Teams", len(result.teams))
            c3.metric("Properties covered", result.properties_covered)
            c4.metric(
                "Avg max bid",
                f"${result.stats.get('avg_max_bid', 0):.1f}M",
            )
            c5, c6, c7, c8 = st.columns(4)
            c5.metric(
                "Avg fair value",
                f"${result.stats.get('avg_predicted_fair_value', 0):.1f}M",
            )
            c6.metric(
                "Avg target LTV",
                f"{result.stats.get('avg_target_ltv', 0):.0%}",
            )
            c7.metric(
                "Avg downside prob",
                f"{result.stats.get('avg_probability_of_downside', 0):.0%}",
            )
            c8.metric(
                "Avg NOI growth",
                f"{result.stats.get('avg_noi_growth', 0):+.1%}",
            )

        with st.expander("Preview submission"):
            st.dataframe(df.head(15), use_container_width=True, hide_index=True)

        if result.ok:
            st.markdown("---")
            st.subheader("Confirm")
            team_name = st.text_input("Team / Fund name", value="Your Fund")
            model_name = st.text_input(
                "Model name",
                value=str(df["model_name"].iloc[0]) if "model_name" in df.columns else "",
            )
            notes = st.text_area("Brief model description (optional)", height=80)

            if st.button("Submit model outputs", type="primary", use_container_width=True):
                st.session_state["submitted_predictions"] = df
                st.session_state["submitted_team_name"] = team_name
                st.session_state["submitted_model_name"] = model_name
                st.session_state["submitted_notes"] = notes
                st.success(f"Model outputs stored for {team_name}. Proceed to the Strategy Card.")

    # Previously submitted
    submitted = st.session_state.get("submitted_predictions")
    if submitted is not None:
        st.markdown("---")
        st.subheader("Stored submission")
        st.caption(
            f"{st.session_state.get('submitted_team_name', 'Your Fund')} · "
            f"{st.session_state.get('submitted_model_name', 'model')} · "
            f"{len(submitted)} rows"
        )

    st.markdown("---")
    st.subheader("Resources")
    col1, col2 = st.columns(2)
    with col1:
        if TEMPLATE_PATH.exists():
            st.download_button(
                "Download prediction_submission_template.csv",
                data=TEMPLATE_PATH.read_bytes(),
                file_name="prediction_submission_template.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info(
                "Template not generated yet. Run "
                "`python scripts/build_student_game_packet.py`."
            )
    with col2:
        if CANDIDATES_PATH.exists():
            st.download_button(
                "Download game_candidates.csv",
                data=CANDIDATES_PATH.read_bytes(),
                file_name="game_candidates.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("Student packet not generated yet.")


def empty_submission_template() -> pd.DataFrame:
    """An empty template with the authoritative column set."""
    return pd.DataFrame(columns=ALL_COLUMNS)


if __name__ == "__main__":
    show()
