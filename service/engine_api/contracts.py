"""
HTTP contracts.

Three concepts that a real investment process keeps separate, and that a badly
designed API blends into one word ("model"):

    FORECAST   what the team's model predicted, built before class
    POLICY     what the team decided it would be willing to pay, derived from that
    DECISION   what the team actually did, in the live round

``max_bid`` and ``target_ltv`` are POLICY. They are never called predictions, and
they are nested under ``policy`` rather than beside the forecast, so the separation
is structural rather than a naming convention someone has to remember.

``extra="forbid"`` on every request model is deliberate: a malformed call must be
rejected with a 422 rather than silently ignored, because a silently dropped field
in this system could be a silently dropped bid.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.game.adjudicator import MANAGEMENT_INVEST_RESERVE_ADDER, ModelPrediction

# ── the three concepts ────────────────────────────────────────────────────


class Forecast(BaseModel):
    """Model output. Produced before class, frozen at check-in."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(default="unnamed-model", max_length=120)
    predicted_fair_value: float = Field(gt=0)
    predicted_noi_growth: float = Field(ge=-1.0, le=1.0)
    probability_of_downside: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted_exit_cap: Optional[float] = Field(default=None, gt=0.0, le=1.0)


class Policy(BaseModel):
    """The team's stated willingness to act. Derived from the forecast, not a prediction."""

    model_config = ConfigDict(extra="forbid")

    max_bid: float = Field(gt=0)
    target_ltv: float = Field(gt=0.0, le=1.0)


class PropertySubmission(BaseModel):
    """One property's forecast and policy, kept in separate namespaces."""

    model_config = ConfigDict(extra="forbid")

    property_id: str
    forecast: Forecast
    policy: Policy


class TeamSpec(BaseModel):
    """A fund entering the game, with its frozen model output."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    team_name: str
    is_bot: bool = False
    submissions: List[PropertySubmission] = Field(default_factory=list)


class Decision(BaseModel):
    """What the manager actually chose to do this round."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    property_id: str
    action: Literal["PASS", "BID"] = "PASS"
    bid: Optional[float] = Field(default=None, gt=0)
    ltv: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    # Supplied by the caller only for the override record; derived on the server
    # from the team's own policy when omitted.
    model_max_bid: Optional[float] = None
    model_target_ltv: Optional[float] = None


class ManagementStance(BaseModel):
    """One fund's operating stance for one owned building, for one round (V2)."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    property_id: str
    stance: Literal["RUN LEAN", "STANDARD", "INVEST & PROTECT"]


def submissions_to_predictions(
    submissions: List[PropertySubmission],
) -> Dict[str, ModelPrediction]:
    """Fold forecast + policy into the engine's prediction type.

    This is the one place the two namespaces meet, so the mapping is explicit: the
    engine's ``max_bid`` comes from POLICY, and its valuation fields from FORECAST.
    """
    out: Dict[str, ModelPrediction] = {}
    for item in submissions:
        out[item.property_id] = ModelPrediction(
            property_id=item.property_id,
            predicted_fair_value=item.forecast.predicted_fair_value,
            predicted_noi_growth=item.forecast.predicted_noi_growth,
            probability_of_downside=item.forecast.probability_of_downside,
            max_bid=item.policy.max_bid,
            target_ltv=item.policy.target_ltv,
            model_name=item.forecast.model_name,
            confidence=item.forecast.confidence,
            predicted_exit_cap=item.forecast.predicted_exit_cap,
        )
    return out


# ── versioned dataset ─────────────────────────────────────────────────────


class BundleSummary(BaseModel):
    """A dataset a professor may choose. Note the absence of a seed."""

    bundle_id: str
    display_name: str
    packet_version: str
    economics_version: str
    description: str = ""


# ── requests and responses ────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    game: str = "cre-investment-committee"
    engine_version: str
    economics_version: str
    economics_digest: str
    schema_version: int
    serde_schema_version: int


class ListBundlesResponse(BaseModel):
    bundles: List[BundleSummary]


class CreateGameStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    teams: List[TeamSpec] = Field(min_length=1)
    scenario: str = "Base Case"
    # V2 course tier. Absent means "whatever the bundle declares", which is the
    # normal path: a dataset and its tier are pinned together. Present, it lets an
    # operator run the published dataset at a different tier (a 310 lab on the 605
    # pool, say). It is safe to offer because the choice is *recorded* -- it is
    # written into the session state and echoed back in the public config, so a
    # session can always be asked which game it is playing.
    course_mode: Optional[str] = None
    management_enabled: Optional[bool] = None


class CreateGameStateResponse(BaseModel):
    bundle: Dict[str, Any]
    state: Dict[str, Any]
    public: Dict[str, Any]


class OpenRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Dict[str, Any]


class OpenRoundResponse(BaseModel):
    state: Dict[str, Any]
    public: Dict[str, Any]
    game_complete: bool


class ResolveRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Dict[str, Any]
    decisions: List[Decision] = Field(default_factory=list)
    # V2: management stances ride the resolve call. They are decisions about the
    # round being closed, so they are submitted in the same window; refusing an
    # unknown stance here would crash a round, so the engine validates and the
    # invalid ones come back in `rejected_stances`.
    management_stances: List[ManagementStance] = Field(default_factory=list)


class RejectedDecision(BaseModel):
    team_id: str
    property_id: str
    reason: str


class RejectedStance(BaseModel):
    team_id: str
    property_id: str
    reason: str


class ResolveRoundResponse(BaseModel):
    state: Dict[str, Any]
    public_results: Dict[str, Any]
    analytics_updates: List[Dict[str, Any]]
    rejected_decisions: List[RejectedDecision]
    # V2: stances refused by the engine (unknown building, disabled management,
    # or an invalid stance for the course mode).
    rejected_stances: List[RejectedStance] = Field(default_factory=list)
    game_complete: bool


class FinalizeGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Dict[str, Any]


class FinalizeGameResponse(BaseModel):
    state: Dict[str, Any]
    standings: List[Dict[str, Any]]
    analytics: List[Dict[str, Any]]
    debrief: Dict[str, Any]
    game_complete: bool
