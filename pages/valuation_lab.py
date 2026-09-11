from __future__ import annotations

import streamlit as st
import pandas as pd


def show():
    st.title("6 · Valuation Lab")
    st.caption("Transparent benchmarks first. Then a baseline regression. You build better models.")

    from src.data.duckdb import DuckDBBackend
    db = DuckDBBackend()
    try:
        props = db.query("SELECT * FROM properties")
    finally:
        db.close()

    st.markdown("---")
    st.subheader("1. Naive valuation benchmarks")
    st.write(
        "Three simple, transparent benchmarks — a straw man to beat:\n"
        "- **NOI / market cap rate** (using the going-in cap by type)\n"
        "- **Median comparable value** by property type\n"
        "- **Price-per-SF benchmark** by property type"
    )
    from src.models.benchmark import naive_value_benchmarks
    market_cap = {
        "Industrial": 0.055,
        "Office": 0.072,
        "Multifamily": 0.052,
        "Retail": 0.065,
    }
    b = naive_value_benchmarks(props, market_cap)
    cols = ["property_id", "property_name", "type", "submarket", "asking_price", "current_noi", "going_in_cap", "noi_cap_value", "median_comp_value", "price_per_sf_value", "benchmark_value"]
    st.dataframe(b[cols].round(3), use_container_width=True, height=320)
    st.caption("These are naive benchmarks. They do not incorporate location, tenant quality, lease structure, or market timing. Students should improve on them.")

    st.markdown("---")
    st.subheader("2. Baseline linear regression")
    st.write(
        "A transparent baseline model trained on the example training data. Coefficients and performance are shown so you can see exactly what it does."
    )
    from src.models.regression import baseline_regression_model, train_ridge_baseline, example_training_data
    reg = baseline_regression_model(seed=20240331, count=30)
    st.metric("Baseline train MAE ($MM)", round(reg["train_mae"], 3))
    st.metric("Baseline train R^2", round(reg["train_r2"], 3))
    st.caption(reg["note"])
    st.markdown("**Coefficients (sorted by absolute magnitude):**")
    st.dataframe(reg["coefficients"], use_container_width=True, height=240)
    st.markdown("**Predicted values vs asking price:**")
    st.dataframe(reg["predictions"], use_container_width=True, height=320)

    ridge = train_ridge_baseline(seed=20240331, count=30)
    st.markdown("---")
    st.subheader("Alternative regularized baseline (Ridge)")
    st.metric("Ridge train MAE ($MM)", round(ridge["train_mae"], 3))
    st.metric("Ridge train R^2", round(ridge["train_r2"], 3))
    st.caption(ridge["note"])

    st.markdown("---")
    st.subheader("3. Download training data + starter notebook")
    train_df = example_training_data(seed=20240331, count=30)
    st.download_button(
        "Download training data (CSV)",
        data=train_df.to_csv(index=False),
        file_name="real605_training_data.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.info(
        "In a full version, a starter notebook (`notebooks/01_baseline_valuation.ipynb`) would walk students "
        "through feature engineering, a baseline model, and how to format predictions for submission."
    )

    st.markdown("---")
    st.subheader("4. Submit your model predictions (optional)")
    st.write(
        "Submit a CSV with: `property_id, predicted_value, predicted_noi, optional probability_of_loss, model_name, model_version`."
    )
    uploaded = st.file_uploader("Upload predictions CSV", type=["csv"])
    if uploaded is not None:
        sub = pd.read_csv(uploaded)
        from src.models.submission import validate_submission, score_submission_predictions
        validation = validate_submission(sub)
        if not validation["ok"]:
            st.error("Submission invalid:")
            for e in validation["errors"]:
                st.error(e)
        else:
            for w in validation["warnings"]:
                st.warning(w)
            st.success("Submission valid. Scoring against actuals (once revealed):")
            st.dataframe(sub, use_container_width=True, height=200)
            # In demo mode, score against the sample predictions we have
            actuals = pd.DataFrame({
                "property_id": reg["predictions"]["property_id"],
                "exit_value": reg["predictions"]["asking_price"],
                "exit_noi": reg["predictions"]["asking_price"] * 0.06,
                "exit_cap": 0.06,
                "probability_of_loss_actual": 0,
            })
            scored = score_submission_predictions(sub, actuals)
            st.dataframe(scored, use_container_width=True, height=240)

    st.markdown("---")
    st.info("Future extension: probabilistic forecasts (prediction intervals / quantile scoring) can plug into the same submission interface.")
    st.page_link("pages/geospatial.py", label="→ Next: Geospatial View", icon="")
