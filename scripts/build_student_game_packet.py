"""
Generate student game packet for pre-class model building.

This script creates:
- historical_training.csv: 1,500-3,000 observations with known outcomes
- game_candidates.csv: 80-120 potential game properties (no future outcomes)
- data_dictionary.csv: Column descriptions
- prediction_submission_template.csv: Template for student predictions
- GAME_RULES.md: Game rules documentation

All data is semi-synthetic: real public geographic/macro context where available,
synthetic financial/transaction targets clearly labeled.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.properties import generate_properties
from src.data.macro import get_macro_data


def generate_historical_training_data(seed: int = 20240331, count: int = 2000) -> pd.DataFrame:
    """
    Generate historical training data with known outcomes.
    
    This represents historical transactions where students can learn
    the relationship between property characteristics and outcomes.
    """
    np.random.seed(seed)
    
    # Property types and submarkets
    property_types = ["Industrial", "Office", "Multifamily", "Retail"]
    submarkets = [
        "Anaheim", "Irvine", "Santa Ana", "Newport Beach", 
        "Costa Mesa", "Huntington Beach", "Fullerton", "Garden Grove"
    ]
    
    data = []
    for i in range(count):
        ptype = np.random.choice(property_types)
        submarket = np.random.choice(submarkets)
        
        # Base characteristics
        building_sf = np.random.lognormal(11.5, 0.6)  # ~100k sf median
        year_built = int(np.random.normal(1995, 15))
        year_built = max(1970, min(2020, year_built))
        
        # Occupancy and NOI
        occupancy = np.random.beta(8, 2)  # Skewed toward high occupancy
        occupancy = max(0.4, min(1.0, occupancy))
        
        # Market rent by type
        base_rent = {
            "Industrial": 1.5,
            "Office": 3.0,
            "Multifamily": 3000,
            "Retail": 3.2
        }[ptype]
        
        market_rent = base_rent * np.random.lognormal(0, 0.15)
        
        # NOI calculation
        if ptype == "Multifamily":
            noi = market_rent * (building_sf / 1000) * 12 * occupancy * 0.65
        else:
            noi = market_rent * building_sf * occupancy * 0.55
        
        # Macro factors (semi-realistic OC context)
        treasury_rate = np.random.normal(0.045, 0.01)
        treasury_rate = max(0.02, min(0.08, treasury_rate))
        
        employment_density = np.random.lognormal(7.5, 0.4)
        
        market_vacancy = np.random.beta(2, 5)  # Generally low vacancy
        market_vacancy = max(0.02, min(0.20, market_vacancy))
        
        # Transaction outcomes (TARGETS - these are what students learn to predict)
        # Cap rate influenced by type, interest rates, vacancy
        base_cap = {
            "Industrial": 0.055,
            "Office": 0.072,
            "Multifamily": 0.052,
            "Retail": 0.065
        }[ptype]
        
        cap_rate = base_cap + (treasury_rate - 0.045) * 0.5 + market_vacancy * 0.1
        cap_rate += np.random.normal(0, 0.005)
        cap_rate = max(0.035, min(0.10, cap_rate))
        
        transaction_price = noi / cap_rate
        
        # Next year NOI (TARGET)
        noi_growth = np.random.normal(0.02, 0.03)
        noi_growth = max(-0.10, min(0.15, noi_growth))
        next_year_noi = noi * (1 + noi_growth)
        
        data.append({
            "property_id": f"H{i:04d}",
            "date": "2024-01-01",
            "property_type": ptype,
            "submarket": submarket,
            "building_sf": round(building_sf),
            "year_built": year_built,
            "occupancy": round(occupancy, 3),
            "noi": round(noi, 3),
            "market_rent": round(market_rent, 2),
            "employment_density": round(employment_density, 2),
            "treasury_rate": round(treasury_rate, 4),
            "market_vacancy": round(market_vacancy, 3),
            "transaction_cap_rate": round(cap_rate, 4),
            "transaction_price": round(transaction_price, 3),  # TARGET
            "next_year_noi": round(next_year_noi, 3),  # TARGET
        })
    
    df = pd.DataFrame(data)
    return df


def generate_game_candidates(seed: int = 20240331, count: int = 100) -> pd.DataFrame:
    """
    Generate game candidate properties WITHOUT future outcomes.
    
    These are the properties students will predict and bid on during the game.
    No future values are exposed - only current characteristics.
    """
    np.random.seed(seed + 1000)  # Different seed from historical
    
    property_types = ["Industrial", "Office", "Multifamily", "Retail"]
    submarkets = [
        "Anaheim", "Irvine", "Santa Ana", "Newport Beach", 
        "Costa Mesa", "Huntington Beach", "Fullerton", "Garden Grove"
    ]
    
    data = []
    for i in range(count):
        ptype = np.random.choice(property_types)
        submarket = np.random.choice(submarkets)
        
        building_sf = np.random.lognormal(11.5, 0.6)
        year_built = int(np.random.normal(1998, 12))
        year_built = max(1975, min(2022, year_built))
        
        occupancy = np.random.beta(8, 2)
        occupancy = max(0.5, min(1.0, occupancy))
        
        base_rent = {
            "Industrial": 1.5,
            "Office": 3.0,
            "Multifamily": 3000,
            "Retail": 3.2
        }[ptype]
        
        market_rent = base_rent * np.random.lognormal(0, 0.12)
        
        if ptype == "Multifamily":
            noi = market_rent * (building_sf / 1000) * 12 * occupancy * 0.65
        else:
            noi = market_rent * building_sf * occupancy * 0.55
        
        treasury_rate = np.random.normal(0.053, 0.008)
        treasury_rate = max(0.03, min(0.07, treasury_rate))
        
        employment_density = np.random.lognormal(7.5, 0.4)
        market_vacancy = np.random.beta(2, 5)
        market_vacancy = max(0.03, min(0.15, market_vacancy))
        
        # Asking price (current market price, NOT a target)
        base_cap = {
            "Industrial": 0.055,
            "Office": 0.072,
            "Multifamily": 0.052,
            "Retail": 0.065
        }[ptype]
        
        cap_rate = base_cap + (treasury_rate - 0.045) * 0.5 + market_vacancy * 0.1
        cap_rate += np.random.normal(0, 0.004)
        cap_rate = max(0.04, min(0.09, cap_rate))
        
        asking_price = noi / cap_rate
        
        # Debt terms (for game mechanics)
        debt_rate = treasury_rate + 0.015
        max_ltv = 0.75 if ptype in ["Industrial", "Multifamily"] else 0.70
        amortization_years = 25 if ptype == "Multifamily" else 20
        
        data.append({
            "property_id": f"GC{i:03d}",
            "property_type": ptype,
            "submarket": submarket,
            "building_sf": round(building_sf),
            "year_built": year_built,
            "occupancy": round(occupancy, 3),
            "noi": round(noi, 3),
            "market_rent": round(market_rent, 2),
            "employment_density": round(employment_density, 2),
            "treasury_rate": round(treasury_rate, 4),
            "market_vacancy": round(market_vacancy, 3),
            "asking_price": round(asking_price, 3),
            "debt_rate": round(debt_rate, 4),
            "max_ltv": round(max_ltv, 3),
            "amortization_years": amortization_years,
        })
    
    df = pd.DataFrame(data)
    return df


def generate_data_dictionary() -> pd.DataFrame:
    """Generate data dictionary describing all columns."""
    data = [
        {
            "column": "property_id",
            "description": "Unique property identifier",
            "type": "string",
            "notes": "Format: H#### for historical, GC### for game candidates"
        },
        {
            "column": "date",
            "description": "Transaction date (historical only)",
            "type": "date",
            "notes": "Historical training data only"
        },
        {
            "column": "property_type",
            "description": "Property asset class",
            "type": "categorical",
            "notes": "Industrial, Office, Multifamily, Retail"
        },
        {
            "column": "submarket",
            "description": "Orange County submarket",
            "type": "categorical",
            "notes": "Anaheim, Irvine, Santa Ana, Newport Beach, etc."
        },
        {
            "column": "building_sf",
            "description": "Building square footage",
            "type": "numeric",
            "notes": "Total rentable area"
        },
        {
            "column": "year_built",
            "description": "Year property was constructed",
            "type": "integer",
            "notes": "Approximate construction year"
        },
        {
            "column": "occupancy",
            "description": "Current occupancy rate",
            "type": "numeric",
            "notes": "0.0 to 1.0 (percentage as decimal)"
        },
        {
            "column": "noi",
            "description": "Net Operating Income (annual)",
            "type": "numeric",
            "notes": "In millions of dollars"
        },
        {
            "column": "market_rent",
            "description": "Current market rent per unit",
            "type": "numeric",
            "notes": "$/SF/year for Industrial/Office/Retail, $/unit/month for Multifamily"
        },
        {
            "column": "employment_density",
            "description": "Local employment density",
            "type": "numeric",
            "notes": "Jobs per square mile (submarket level)"
        },
        {
            "column": "treasury_rate",
            "description": "10-year Treasury rate",
            "type": "numeric",
            "notes": "Risk-free rate at time of analysis"
        },
        {
            "column": "market_vacancy",
            "description": "Market vacancy rate by property type",
            "type": "numeric",
            "notes": "0.0 to 1.0 (percentage as decimal)"
        },
        {
            "column": "transaction_cap_rate",
            "description": "Transaction cap rate (historical only)",
            "type": "numeric",
            "notes": "Historical training data only - NOI / Price"
        },
        {
            "column": "transaction_price",
            "description": "Transaction sale price (historical only)",
            "type": "numeric",
            "notes": "Historical TARGET - what students learn to predict"
        },
        {
            "column": "next_year_noi",
            "description": "NOI one year forward (historical only)",
            "type": "numeric",
            "notes": "Historical TARGET - what students learn to forecast"
        },
        {
            "column": "asking_price",
            "description": "Current asking price (game candidates only)",
            "type": "numeric",
            "notes": "Game candidates only - current market price"
        },
        {
            "column": "debt_rate",
            "description": "Interest rate for debt financing",
            "type": "numeric",
            "notes": "Game candidates only - spread over Treasury"
        },
        {
            "column": "max_ltv",
            "description": "Maximum loan-to-value ratio",
            "type": "numeric",
            "notes": "Game candidates only - lender constraint"
        },
        {
            "column": "amortization_years",
            "description": "Loan amortization period",
            "type": "integer",
            "notes": "Game candidates only - years to amortize"
        },
    ]
    return pd.DataFrame(data)


def generate_prediction_template(game_candidates: pd.DataFrame) -> pd.DataFrame:
    """Generate template for student prediction submissions."""
    template = game_candidates[["property_id"]].copy()
    template["predicted_fair_value"] = 0.0
    template["predicted_noi_growth"] = 0.0
    template["probability_of_downside"] = 0.5
    template["max_bid"] = 0.0
    template["target_ltv"] = 0.0
    template["model_name"] = ""
    template["model_version"] = ""
    template["confidence"] = 0.5
    template["predicted_exit_cap"] = 0.0
    template["notes"] = ""
    return template


def generate_game_rules() -> str:
    """Generate GAME_RULES.md documentation."""
    return """# REAL 605 CRE Investment Game Rules

## Overview

This is a competitive real estate investment simulation where teams use their analytical models to make acquisition decisions. The game tests both **model quality** and **investment decision-making**.

## Game Structure

### Before Class
1. Download the student packet containing:
   - `historical_training.csv` - 2,000 historical transactions with known outcomes
   - `game_candidates.csv` - 100 potential game properties (no future outcomes)
   - `data_dictionary.csv` - Column descriptions
   - `prediction_submission_template.csv` - Template for your predictions

2. Build your model externally using Excel, Python, R, or any tool you prefer.

3. Generate predictions for all 100 game candidate properties.

4. Upload your predictions via the Model Check-In page before class begins.

### During Class
1. **Practice Round** (5 minutes, non-scored): Learn the interface
2. **Round 1** (8 minutes): First competitive acquisitions
3. **Round 2** (8 minutes): Portfolio evolves, market updates
4. **Round 3** (8 minutes): Continue strategy
5. **Round 4** (8 minutes): Final acquisitions
6. **Debrief** (15-20 minutes): Review results

## Starting Capital

Each team begins with **$100M equity capital**.

You can bid on multiple properties across rounds, but you must manage your capital carefully. Overbidding in early rounds leaves you with fewer opportunities later.

## Property Acquisition

### Sealed-Bid Auctions
- All teams see the same 4 properties each round
- Each team submits a private bid (PASS or BID with price and LTV)
- Highest valid bid wins the property
- Winner pays their submitted price
- If highest bid < seller's reserve price, property does not sell

### Bid Constraints
- Bid must be > $0
- LTV must be between 0 and property max LTV (typically 70-75%)
- You must have sufficient cash: `Cash >= Bid Price × (1 - LTV)`
- Round must be open for submissions

### Tie-Breaking
If bids are tied:
1. Lower LTV (higher equity) wins
2. If still tied, deterministic seeded tie-breaker

## Your Model Predictions

Before the game, you submitted predictions for each property including:
- **Predicted Fair Value** - What your model thinks the property is worth
- **Predicted NOI Growth** - Expected annual NOI change
- **Probability of Downside** - Likelihood of negative outcome
- **Max Bid** - Maximum price your model recommends
- **Target LTV** - Leverage level your model recommends

During the game, you'll see **YOUR MODEL** panel beside each property showing these predictions. The game does NOT calculate these - it displays what YOUR model said.

## Human Overrides

The game tracks when you override your own model:
- If you bid above your model's max bid → recorded as override
- If you use different LTV than target → recorded as override

After results, you'll see whether overrides helped or hurt. This creates an important learning artifact: when should you trust your model vs. human judgment?

## Market Evolution

Each round represents approximately one year. Between rounds:
- Interest rates may change
- Employment growth/vacancy evolve
- Property NOI changes
- Cap rates shift
- Property values reprice

Properties acquired in Round 1 remain in your portfolio through Rounds 2-4. You must live with early decisions.

## Scoring

### Game Leaderboard (Competitive Ranking)
Primary metric: **Ending Fund NAV**
- NAV = Cash + Property Values - Debt
- Also shows: cumulative return, cash, debt, portfolio LTV

### Analytics Leaderboard (Model Quality)
Separate evaluation of analytical performance:
- Valuation MAE (Mean Absolute Error)
- NOI Forecast MAE
- Probability calibration (Brier Score)
- Performance vs. naive benchmark
- Human override contribution

## Winning

The team with the highest ending NAV wins the game.

However, the professor will separately evaluate model quality using the analytics leaderboard. A good model with poor decision-making can lose. A mediocre model with excellent decision discipline can win.

## Key Learning Objectives

1. **Model Quality** - Can you build accurate valuation and forecasting models?
2. **Decision Discipline** - Can you follow your model's recommendations?
3. **Strategic Capital Allocation** - Can you allocate scarce capital effectively?
4. **Override Judgment** - When should you trust vs. override your model?
5. **Competitive Strategy** - How much should you pay to win vs. maintain discipline?

## Important Notes

- The practice round does NOT count toward final standings
- All market movements follow explicit economic rules (not arbitrary events)
- Randomness is seeded and reproducible
- The adjudicator (rules engine) determines all outcomes - no opaque AI
- Your model predictions are private - other teams cannot see them
- Historical training data has known outcomes for learning
- Game candidate data has NO future outcomes - you must predict them

## Technical Details

- All randomness uses deterministic seeds
- Market evolution follows explicit functions in the adjudicator
- Bid validation, auction resolution, and portfolio updates are inspectable code
- Full world state (all bids, reserve prices) is hidden from players
- Each team sees only their own observations
"""


def main():
    """Generate all student packet files."""
    output_dir = Path("student_packet")
    output_dir.mkdir(exist_ok=True)
    
    print("Generating student game packet...")
    
    # Generate historical training data
    print("  - Generating historical training data...")
    historical = generate_historical_training_data(seed=20240331, count=2000)
    historical.to_csv(output_dir / "historical_training.csv", index=False)
    print(f"    Generated {len(historical)} historical observations")
    
    # Generate game candidates
    print("  - Generating game candidates...")
    candidates = generate_game_candidates(seed=20240331, count=100)
    candidates.to_csv(output_dir / "game_candidates.csv", index=False)
    print(f"    Generated {len(candidates)} game candidate properties")
    
    # Generate data dictionary
    print("  - Generating data dictionary...")
    data_dict = generate_data_dictionary()
    data_dict.to_csv(output_dir / "data_dictionary.csv", index=False)
    
    # Generate prediction template
    print("  - Generating prediction submission template...")
    template = generate_prediction_template(candidates)
    template.to_csv(output_dir / "prediction_submission_template.csv", index=False)
    
    # Generate game rules
    print("  - Generating game rules documentation...")
    rules = generate_game_rules()
    (output_dir / "GAME_RULES.md").write_text(rules)
    
    print(f"\nStudent packet generated successfully in {output_dir}/")
    print("Files created:")
    print("  - historical_training.csv")
    print("  - game_candidates.csv")
    print("  - data_dictionary.csv")
    print("  - prediction_submission_template.csv")
    print("  - GAME_RULES.md")


if __name__ == "__main__":
    main()
