"""
Create demo team bots with different model archetypes.

For professor demonstration without real students:
- Value Model: good fair-value estimates, conservative bids
- Growth Model: aggressive NOI assumptions
- Risk Model: conservative downside forecasts
- Noisy Model: weaker predictions / inconsistent bids
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.properties import generate_properties


def generate_value_model_predictions(properties: pd.DataFrame, seed: int = 20240331) -> pd.DataFrame:
    """
    Value Model: Good fair-value estimates, conservative bids.
    
    Characteristics:
    - Accurate valuation (small error around true value)
    - Disciplined bid ceiling: will pay up to 95-99% of its own fair value
    - Moderate LTV (55-65%)
    - Reasonable downside risk estimates

    Note on bid levels
    ------------------
    The seller's hidden reserve is drawn from 90-95% of the asking price. A model
    whose bid ceiling sits *below* that band never transacts, never tests its
    forecast, and finishes at exactly its starting NAV -- which makes for a flat,
    uninformative classroom demo. Each archetype's bid ceiling is therefore set so
    that its discipline is visible in *contested* deals rather than silently
    pricing it out of the market entirely.
    """
    np.random.seed(seed)
    
    predictions = []
    for _, row in properties.iterrows():
        # Good valuation accuracy (±5% error)
        valuation_error = np.random.normal(0, 0.05)
        predicted_value = row["asking_price"] * (1 + valuation_error)
        
        # Conservative NOI growth (1-3%)
        predicted_noi_growth = np.random.uniform(0.01, 0.03)
        
        # Conservative max bid (85-90% of predicted value)
        max_bid = predicted_value * np.random.uniform(0.95, 0.99)
        
        # Moderate LTV
        target_ltv = np.random.uniform(0.55, 0.65)
        
        # Reasonable downside risk (15-25%)
        probability_of_downside = np.random.uniform(0.15, 0.25)
        
        predictions.append({
            "property_id": row["property_id"],
            "predicted_fair_value": round(predicted_value, 3),
            "predicted_noi": round(row["current_noi"] * (1 + predicted_noi_growth), 3),
            "predicted_noi_growth": round(predicted_noi_growth, 4),
            "probability_of_downside": round(probability_of_downside, 3),
            "max_bid": round(max_bid, 3),
            "target_ltv": round(target_ltv, 3),
            "model_name": "Value Model",
            "model_version": "1.0",
            "confidence": np.random.uniform(0.7, 0.9),
        })
    
    return pd.DataFrame(predictions)


def generate_growth_model_predictions(properties: pd.DataFrame, seed: int = 20240332) -> pd.DataFrame:
    """
    Growth Model: Aggressive NOI assumptions.
    
    Characteristics:
    - Optimistic valuation (assumes growth)
    - Aggressive bids (90-95% of predicted value)
    - Higher LTV (65-75%)
    - Low downside risk estimates (overconfident)
    """
    np.random.seed(seed)
    
    predictions = []
    for _, row in properties.iterrows():
        # Optimistic valuation (mild upward bias, wider error than Value)
        valuation_error = np.random.normal(0.01, 0.05)
        predicted_value = row["asking_price"] * (1 + valuation_error)
        
        # Aggressive NOI growth (4-7%)
        predicted_noi_growth = np.random.uniform(0.04, 0.07)
        
        # Aggressive max bid (99-103% of predicted value)
        max_bid = predicted_value * np.random.uniform(0.99, 1.03)
        
        # Higher LTV
        target_ltv = np.random.uniform(0.65, 0.75)
        
        # Low downside risk (overconfident)
        probability_of_downside = np.random.uniform(0.05, 0.15)
        
        predictions.append({
            "property_id": row["property_id"],
            "predicted_fair_value": round(predicted_value, 3),
            "predicted_noi": round(row["current_noi"] * (1 + predicted_noi_growth), 3),
            "predicted_noi_growth": round(predicted_noi_growth, 4),
            "probability_of_downside": round(probability_of_downside, 3),
            "max_bid": round(max_bid, 3),
            "target_ltv": round(target_ltv, 3),
            "model_name": "Growth Model",
            "model_version": "1.0",
            "confidence": np.random.uniform(0.8, 0.95),
        })
    
    return pd.DataFrame(predictions)


def generate_risk_model_predictions(properties: pd.DataFrame, seed: int = 20240333) -> pd.DataFrame:
    """
    Risk Model: Conservative downside forecasts.
    
    Characteristics:
    - Cautious valuation (mild downward bias)
    - Conservative bid ceiling (96-99% of its own fair value) -- this is what
      makes it disciplined: it will not chase an asset past its estimate
    - Low LTV (45-55%), the lowest leverage of the four
    - High downside risk estimates, and it sits out deals it cannot price
    """
    np.random.seed(seed)
    
    predictions = []
    for _, row in properties.iterrows():
        # Cautious valuation (mild downward bias)
        valuation_error = np.random.normal(-0.01, 0.04)
        predicted_value = row["asking_price"] * (1 + valuation_error)
        
        # Conservative NOI growth (0-2%)
        predicted_noi_growth = np.random.uniform(0.0, 0.02)
        
        # Conservative max bid (96-99% of predicted value). Discipline is shown
        # by refusing to chase, not by bidding below every possible reserve.
        max_bid = predicted_value * np.random.uniform(0.96, 0.99)
        
        # Low LTV
        target_ltv = np.random.uniform(0.45, 0.55)
        
        # High downside risk (cautious)
        probability_of_downside = np.random.uniform(0.30, 0.45)
        
        predictions.append({
            "property_id": row["property_id"],
            "predicted_fair_value": round(predicted_value, 3),
            "predicted_noi": round(row["current_noi"] * (1 + predicted_noi_growth), 3),
            "predicted_noi_growth": round(predicted_noi_growth, 4),
            "probability_of_downside": round(probability_of_downside, 3),
            "max_bid": round(max_bid, 3),
            "target_ltv": round(target_ltv, 3),
            "model_name": "Risk Model",
            "model_version": "1.0",
            "confidence": np.random.uniform(0.6, 0.8),
        })
    
    return pd.DataFrame(predictions)


def generate_noisy_model_predictions(properties: pd.DataFrame, seed: int = 20240334) -> pd.DataFrame:
    """
    Noisy Model: Weaker predictions / inconsistent bids.
    
    Characteristics:
    - Poor valuation accuracy (high variance, ±15% error)
    - Inconsistent bid discipline (90-102% of predicted value)
    - Variable LTV (40-75%)
    - Random downside risk estimates
    - Lower confidence
    """
    np.random.seed(seed)
    
    predictions = []
    for _, row in properties.iterrows():
        # Poor valuation accuracy (high variance)
        valuation_error = np.random.normal(0, 0.15)
        predicted_value = row["asking_price"] * (1 + valuation_error)
        
        # Variable NOI growth (-2% to 6%)
        predicted_noi_growth = np.random.uniform(-0.02, 0.06)
        
        # Inconsistent bid discipline (90-102% of predicted value)
        max_bid = predicted_value * np.random.uniform(0.90, 1.02)
        
        # Variable LTV
        target_ltv = np.random.uniform(0.40, 0.75)
        
        # Random downside risk
        probability_of_downside = np.random.uniform(0.10, 0.50)
        
        predictions.append({
            "property_id": row["property_id"],
            "predicted_fair_value": round(predicted_value, 3),
            "predicted_noi": round(row["current_noi"] * (1 + predicted_noi_growth), 3),
            "predicted_noi_growth": round(predicted_noi_growth, 4),
            "probability_of_downside": round(probability_of_downside, 3),
            "max_bid": round(max_bid, 3),
            "target_ltv": round(target_ltv, 3),
            "model_name": "Noisy Model",
            "model_version": "1.0",
            "confidence": np.random.uniform(0.4, 0.7),
        })
    
    return pd.DataFrame(predictions)


def create_demo_teams(
    seed: int = 20240331,
    count: int = 100,
    save: bool = True,
    verbose: bool = True,
):
    """Create all demo team predictions.

    ``save=False`` keeps the call side-effect free, which matters anywhere the
    demo teams are needed in-process (the app, tests, verification scripts)
    rather than as a build step. ``verbose=False`` silences progress output.
    """
    def say(*args) -> None:
        if verbose:
            print(*args)

    say("Generating demo team predictions...")

    # Generate properties
    properties = generate_properties(seed=seed, count=count)

    output_dir = Path("demo_teams")
    if save:
        output_dir.mkdir(exist_ok=True)

    def emit(frame: pd.DataFrame, filename: str) -> pd.DataFrame:
        if save:
            frame.to_csv(output_dir / filename, index=False)
        return frame

    say("  - Generating Value Model predictions...")
    value_predictions = emit(
        generate_value_model_predictions(properties, seed),
        "value_model_predictions.csv",
    )
    say(f"    Generated {len(value_predictions)} predictions")

    say("  - Generating Growth Model predictions...")
    growth_predictions = emit(
        generate_growth_model_predictions(properties, seed + 1),
        "growth_model_predictions.csv",
    )
    say(f"    Generated {len(growth_predictions)} predictions")

    say("  - Generating Risk Model predictions...")
    risk_predictions = emit(
        generate_risk_model_predictions(properties, seed + 2),
        "risk_model_predictions.csv",
    )
    say(f"    Generated {len(risk_predictions)} predictions")

    say("  - Generating Noisy Model predictions...")
    noisy_predictions = emit(
        generate_noisy_model_predictions(properties, seed + 3),
        "noisy_model_predictions.csv",
    )
    say(f"    Generated {len(noisy_predictions)} predictions")

    # Generate summary
    say("\nDemo Team Summary:")
    say("  Value Model: Conservative, accurate valuations, 95-99% bid ceiling")
    say("  Growth Model: Aggressive, optimistic forecasts, 100-106% bid ceiling")
    say("  Risk Model: Cautious, downside-focused, 90-95% bid ceiling")
    say("  Noisy Model: Inconsistent, high variance, 90-102% bid ceiling")

    if save:
        say(f"\nDemo team predictions saved to {output_dir}/")
        say("Files created:")
        say("  - value_model_predictions.csv")
        say("  - growth_model_predictions.csv")
        say("  - risk_model_predictions.csv")
        say("  - noisy_model_predictions.csv")

    return {
        "Value Model": value_predictions,
        "Growth Model": growth_predictions,
        "Risk Model": risk_predictions,
        "Noisy Model": noisy_predictions,
    }


def load_demo_team_predictions(team_name: str, properties: pd.DataFrame) -> pd.DataFrame:
    """Load predictions for a specific demo team."""
    demo_dir = Path("demo_teams")
    
    team_files = {
        "Value Model": "value_model_predictions.csv",
        "Growth Model": "growth_model_predictions.csv",
        "Risk Model": "risk_model_predictions.csv",
        "Noisy Model": "noisy_model_predictions.csv",
    }
    
    if team_name not in team_files:
        raise ValueError(f"Unknown demo team: {team_name}")
    
    file_path = demo_dir / team_files[team_name]
    if not file_path.exists():
        raise FileNotFoundError(f"Demo team file not found: {file_path}")
    
    predictions = pd.read_csv(file_path)
    
    # Filter to only properties in the current game
    property_ids = properties["property_id"].tolist()
    predictions = predictions[predictions["property_id"].isin(property_ids)]
    
    return predictions


if __name__ == "__main__":
    create_demo_teams(seed=20240331, count=100)
