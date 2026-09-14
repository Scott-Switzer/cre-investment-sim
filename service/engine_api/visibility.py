"""
The hidden-information boundary.

This game's integrity rests entirely on information the player must not have:

* the **seller's reserve price** on each offered property, and
* every **realised future outcome** (the year's NOI growth, cap rate and value).

If either reaches a browser before the round resolves, the exercise is over: a
student can solve the auction by reading the answer instead of by modelling. The
classification below is therefore not documentation -- it is enforced by
``assert_no_leaks``, which every public serialiser calls.

One rule with no exceptions: **the full engine snapshot is server-only.** Public
payloads are built by *naming* the fields they expose, never by subtracting fields
from a snapshot. Subtraction fails open the first time someone adds a field.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Set


class Visibility(str, Enum):
    """When a field may cross the server boundary."""

    # Safe to show a player before they decide.
    PUBLIC_BEFORE_ROUND = "public_before_round"
    # Only the owning fund (and the instructor). Never another fund.
    PRIVATE_TEAM_ONLY = "private_team_only"
    # Hidden until the round is resolved, then revealed.
    SERVER_SECRET_UNTIL_RESOLVE = "server_secret_until_resolve"
    # Published once the round or the game is over.
    PUBLIC_AFTER_RESOLVE = "public_after_resolve"
    # Never leaves the server, under any phase.
    SERVER_ONLY_ALWAYS = "server_only_always"


FIELD_VISIBILITY: Dict[str, Visibility] = {
    # ── property identity and physical ──
    "property_id": Visibility.PUBLIC_BEFORE_ROUND,
    "property_name": Visibility.PUBLIC_BEFORE_ROUND,
    "property_type": Visibility.PUBLIC_BEFORE_ROUND,
    "submarket": Visibility.PUBLIC_BEFORE_ROUND,
    "building_sf": Visibility.PUBLIC_BEFORE_ROUND,
    "units": Visibility.PUBLIC_BEFORE_ROUND,
    "year_built": Visibility.PUBLIC_BEFORE_ROUND,
    # ── property operations (the underwriting drawer) ──
    "current_noi": Visibility.PUBLIC_BEFORE_ROUND,
    "occupancy": Visibility.PUBLIC_BEFORE_ROUND,
    "market_rent": Visibility.PUBLIC_BEFORE_ROUND,
    "in_place_rent": Visibility.PUBLIC_BEFORE_ROUND,
    "walt": Visibility.PUBLIC_BEFORE_ROUND,
    "tenant_concentration": Visibility.PUBLIC_BEFORE_ROUND,
    "opex_ratio": Visibility.PUBLIC_BEFORE_ROUND,
    "lease_expiry_profile": Visibility.PUBLIC_BEFORE_ROUND,
    "property_quality": Visibility.PUBLIC_BEFORE_ROUND,
    "primary_risk": Visibility.PUBLIC_BEFORE_ROUND,
    # Descriptive building-condition feature. NOT a cash charge; the recurring
    # charge is CAPITAL_RESERVE_RATE. Named so the two cannot be confused.
    "indicative_capex_exposure": Visibility.PUBLIC_BEFORE_ROUND,
    # ── capital markets ──
    "asking_price": Visibility.PUBLIC_BEFORE_ROUND,
    "current_cap": Visibility.PUBLIC_BEFORE_ROUND,
    "going_in_cap": Visibility.PUBLIC_BEFORE_ROUND,
    "debt_rate": Visibility.PUBLIC_BEFORE_ROUND,
    "max_ltv": Visibility.PUBLIC_BEFORE_ROUND,
    "amortization_years": Visibility.PUBLIC_BEFORE_ROUND,
    "acquisition_cost_rate": Visibility.PUBLIC_BEFORE_ROUND,
    "capital_reserve_rate": Visibility.PUBLIC_BEFORE_ROUND,
    # ── THE SECRETS ──
    "reserve_price": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "noi_growth_actual": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "cap_rate_actual": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "exit_value": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "exit_noi": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "occupancy_change": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "all_bids": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "bid_price": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    "ltv": Visibility.SERVER_SECRET_UNTIL_RESOLVE,
    # ── per-fund private ──
    "model_predictions": Visibility.PRIVATE_TEAM_ONLY,
    "override_history": Visibility.PRIVATE_TEAM_ONLY,
    "cumulative_income": Visibility.PRIVATE_TEAM_ONLY,
    "cumulative_interest": Visibility.PRIVATE_TEAM_ONLY,
    "cumulative_purchase_price": Visibility.PRIVATE_TEAM_ONLY,
    "cumulative_acquisition_costs": Visibility.PRIVATE_TEAM_ONLY,
    "cumulative_reserves": Visibility.PRIVATE_TEAM_ONLY,
    "properties": Visibility.PRIVATE_TEAM_ONLY,
    # ── published after resolve ──
    "winning_team_id": Visibility.PUBLIC_AFTER_RESOLVE,
    "winning_bid": Visibility.PUBLIC_AFTER_RESOLVE,
    "winning_ltv": Visibility.PUBLIC_AFTER_RESOLVE,
    "sold": Visibility.PUBLIC_AFTER_RESOLVE,
    "nav": Visibility.PUBLIC_AFTER_RESOLVE,
    "standings": Visibility.PUBLIC_AFTER_RESOLVE,
    # ── never leaves the server ──
    "config": Visibility.SERVER_ONLY_ALWAYS,
    "seed": Visibility.SERVER_ONLY_ALWAYS,
    "adjudicator_seed": Visibility.SERVER_ONLY_ALWAYS,
    "adjudicator_rng_state": Visibility.SERVER_ONLY_ALWAYS,
    "all_properties": Visibility.SERVER_ONLY_ALWAYS,
    "round_history": Visibility.SERVER_ONLY_ALWAYS,
    "market_history": Visibility.SERVER_ONLY_ALWAYS,
    "current_round_result": Visibility.SERVER_ONLY_ALWAYS,
    "submitted_bids": Visibility.SERVER_ONLY_ALWAYS,
    "event_log": Visibility.SERVER_ONLY_ALWAYS,
}

def _keys(*visibilities: Visibility) -> FrozenSet[str]:
    wanted = set(visibilities)
    return frozenset(k for k, v in FIELD_VISIBILITY.items() if v in wanted)


SERVER_ONLY_KEYS: FrozenSet[str] = _keys(Visibility.SERVER_ONLY_ALWAYS)
TEAM_PRIVATE_KEYS: FrozenSet[str] = _keys(Visibility.PRIVATE_TEAM_ONLY)
PRE_RESOLVE_SECRET_KEYS: FrozenSet[str] = _keys(Visibility.SERVER_SECRET_UNTIL_RESOLVE)

# A payload every fund can see: no engine internals, no other fund's private
# state, and no pre-decision secrets. This is the set a round payload is checked
# against, and leaking the reserve here is the mistake that ends the exercise.
FORBIDDEN_IN_BROADCAST: FrozenSet[str] = (
    SERVER_ONLY_KEYS | TEAM_PRIVATE_KEYS | PRE_RESOLVE_SECRET_KEYS
)

# After the round resolves the reserve and the realised outcome are deliberately
# published, so only server internals and other funds' private state stay hidden.
FORBIDDEN_IN_RESULTS: FrozenSet[str] = SERVER_ONLY_KEYS | TEAM_PRIVATE_KEYS

# A payload addressed to ONE fund may carry that fund's own holdings, model and
# override record -- so only engine internals are forbidden. Single-team scoping
# is enforced separately, because that is the leak this payload could cause.
FORBIDDEN_IN_TEAM_VIEW: FrozenSet[str] = SERVER_ONLY_KEYS

# Backwards-compatible aliases.
FORBIDDEN_IN_PUBLIC: FrozenSet[str] = FORBIDDEN_IN_RESULTS
FORBIDDEN_BEFORE_RESOLVE: FrozenSet[str] = FORBIDDEN_IN_BROADCAST


class LeakError(AssertionError):
    """A public payload contained information the player must not have."""


def required_phase_for(field: str) -> Visibility:
    return FIELD_VISIBILITY.get(field, Visibility.SERVER_ONLY_ALWAYS)


def collect_keys(obj: Any, out: Set[str] | None = None) -> Set[str]:
    """Every key name appearing anywhere in a payload, at any depth."""
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.add(str(key))
            collect_keys(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            collect_keys(item, out)
    return out


def collect_numbers(obj: Any, out: List[float] | None = None) -> List[float]:
    """Every numeric value in a payload, for value-level leak checks."""
    if out is None:
        out = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            collect_numbers(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            collect_numbers(item, out)
    return out


def assert_single_team(payload: Any, team_id: str, label: str) -> None:
    """Fail if a team-addressed payload mentions any other fund's id.

    The strongest form of the "other teams' model outputs stay private" rule: a
    payload built for one fund must name exactly that fund and no other.
    """
    found = collect_team_ids(payload)
    others = {t for t in found if t != team_id}
    if others:
        raise LeakError(
            f"{label} is addressed to '{team_id}' but also names {sorted(others)}"
        )


def collect_team_ids(payload: Any, out: Set[str] | None = None) -> Set[str]:
    """Team identifiers appearing in a payload, from known team-id-bearing keys."""
    if out is None:
        out = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in TEAM_ID_KEYS and isinstance(value, str) and value:
                out.add(value)
            elif key in TEAM_ID_MAP_KEYS and isinstance(value, dict):
                out.update(str(k) for k in value)
            else:
                collect_team_ids(value, out)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            collect_team_ids(item, out)
    return out


TEAM_ID_KEYS: FrozenSet[str] = frozenset(
    {"team_id", "winning_team_id", "team", "fund_id", "owner_team_id"}
)
TEAM_ID_MAP_KEYS: FrozenSet[str] = frozenset(
    {"teams", "portfolio_updates", "holdings", "funds"}
)


def assert_no_leaks(
    payload: Any,
    label: str,
    forbidden: Iterable[str] = FORBIDDEN_IN_BROADCAST,
    secret_values: Dict[str, float] | None = None,
) -> None:
    """Fail if a public payload exposes a forbidden key or a secret value.

    Both checks matter. A key check catches the obvious mistake; the value check
    catches the subtle one -- computing the reserve and shipping the number under
    an innocent name like ``min_price`` or ``floor``.
    """
    forbidden_set = {str(k) for k in forbidden}
    present = collect_keys(payload) & forbidden_set
    if present:
        raise LeakError(
            f"{label} leaks forbidden field(s): {sorted(present)}"
        )

    if secret_values:
        numbers = collect_numbers(payload)
        for name, secret in secret_values.items():
            if secret is None:
                continue
            # Exact match only. Reserve prices are derived values, so a rounded or
            # transformed copy is a different failure mode than this check targets.
            if any(abs(n - float(secret)) < 1e-9 for n in numbers):
                raise LeakError(
                    f"{label} leaks the secret value of {name} ({secret})"
                )
