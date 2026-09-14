"""
Golden contract fixtures.

There is no TypeScript economics to keep in parity, so the parity-bug class that
the original plan was written to defend against does not exist. What replaces it is
a **frozen contract**: a set of requests and the exact responses the verified
Python engine produced for them.

Two rules make these fixtures worth having rather than merely numerous:

1. **They are emitted by the engine, never typed by hand.** A hand-written
   expectation is a second implementation of the rules, which is the thing this
   whole approach exists to avoid.
2. **The generator and the tests share this one module.** If the generator
   normalised timestamps one way and the tests another, the fixtures would encode
   one view of the contract and the check would assert another -- drift hidden
   inside the mechanism meant to catch drift.

Why the engine state is stored separately
-----------------------------------------
A `GameManager` snapshot is ~115 KB of JSON, and almost every fixture carries one
in both directions. Inlining them would put megabytes into git and make every
fixture file unreadable. Instead a state is written once to `_states/<name>.json.gz`
and referenced as::

    {"$state_ref": "_states/round1-open.json.gz", "sha256": "<digest>"}

The digest is of the uncompressed canonical JSON, so a reference is verifiable:
the tests compare the digest of what the service actually returned against the
digest recorded here. Nothing is skipped by the indirection -- the bulky part is
still asserted, byte for byte, just not duplicated.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from src.game.manager import GameManager

from . import bundles, serde
from .app import app

# Bump when the fixture layout or the normalisation changes.
FIXTURE_SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = REPO_ROOT / "tests" / "contracts" / "engine_api"
STATE_DIRNAME = "_states"
STATE_DIR = CONTRACT_DIR / STATE_DIRNAME
STUDENT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "student_submission_realistic.csv"

# Wall-clock values are the only thing in an engine response that legitimately
# differs between two identical calls. They are replaced, not dropped, so the shape
# of the event log is still part of the contract.
NORMALISED_TIME = "1970-01-01T00:00:00"

STATE_REF_KEY = "$state_ref"


# ── canonicalisation ──────────────────────────────────────────────────────


def normalise(payload: Any) -> Any:
    """Replace wall-clock timestamps so two identical runs compare equal."""
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            if key == "at" and isinstance(value, str):
                out[key] = NORMALISED_TIME
            else:
                out[key] = normalise(value)
        return out
    if isinstance(payload, list):
        return [normalise(item) for item in payload]
    return payload


def canonical_digest(payload: Any) -> str:
    """SHA-256 over canonical JSON. Used for state references and tamper checks."""
    return hashlib.sha256(serde.dumps(payload).encode()).hexdigest()


def state_digest(state: Dict[str, Any]) -> str:
    """Digest of a state snapshot, taken over its *normalised* form.

    Digests must be taken after normalisation, not before. An engine state carries
    an event log whose entries are timestamped to the second, so digesting the raw
    snapshot makes the same state hash differently depending on when it was built:
    the fixture check would then pass or fail according to the clock. Normalising
    first means the digest describes the state, not the moment it was produced.
    """
    return canonical_digest(normalise(state))


def _write_state(name: str, state: Dict[str, Any]) -> Dict[str, str]:
    """Persist a state snapshot and return the reference that replaces it inline."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    relative = f"{STATE_DIRNAME}/{name}.json.gz"
    payload = serde.dumps(state).encode()
    (CONTRACT_DIR / relative).write_bytes(gzip.compress(payload, mtime=0))
    return {STATE_REF_KEY: relative, "sha256": state_digest(state)}


def read_state(contract_dir: Path, reference: Dict[str, str]) -> Dict[str, Any]:
    """Load a state a fixture refers to, verifying it is the state that was frozen."""
    path = contract_dir / reference[STATE_REF_KEY]
    with gzip.open(path, "rb") as handle:
        state = json.loads(handle.read().decode())
    digest = state_digest(state)
    if digest != reference.get("sha256"):
        raise ValueError(
            f"state {reference[STATE_REF_KEY]} has digest {digest[:12]}… but the "
            f"fixture recorded {reference.get('sha256', '')[:12]}…"
        )
    return state


def is_state_ref(value: Any) -> bool:
    return isinstance(value, dict) and STATE_REF_KEY in value



# ── the fixture record ────────────────────────────────────────────────────


@dataclass
class Fixture:
    """One request and the response the engine produced for it."""

    name: str
    method: str
    path: str
    status: int
    request_body: Optional[Dict[str, Any]] = None
    response_body: Optional[Dict[str, Any]] = None
    notes: str = ""


# ── submissions ───────────────────────────────────────────────────────────


def student_submissions() -> List[Dict[str, Any]]:
    """The shipped student model, in the forecast/policy shape the API expects."""
    from src.game.submission import load_submission

    predictions = load_submission(str(STUDENT_FIXTURE))
    out = []
    for prediction in predictions.values():
        out.append({
            "property_id": prediction.property_id,
            "forecast": {
                "model_name": prediction.model_name or "student_gbm_v1",
                "predicted_fair_value": prediction.predicted_fair_value,
                "predicted_noi_growth": prediction.predicted_noi_growth,
                "probability_of_downside": prediction.probability_of_downside,
                "confidence": prediction.confidence,
            },
            "policy": {
                "max_bid": prediction.max_bid,
                "target_ltv": prediction.target_ltv,
            },
        })
    return out


def _fresh_pool() -> Dict[str, Any]:
    """The pool for the published bundle, so bids can be aimed at real reserves.

    Fixture generation is allowed to know the reserves -- it runs server-side and
    the fixtures are test artifacts. What must never happen is a *player* payload
    carrying one, which `visibility.py` enforces and
    `tests/test_engine_api_visibility.py` checks.
    """
    bundle = bundles.load_bundle(bundles.list_bundles()[0].bundle_id)
    game = GameManager(bundles.game_config_for_bundle(bundle))
    return game.all_properties


def policy_of(submissions: List[Dict[str, Any]], property_id: str) -> Dict[str, float]:
    for item in submissions:
        if item["property_id"] == property_id:
            return item["policy"]
    return {"max_bid": 0.0, "target_ltv": 0.6}


# ── building ──────────────────────────────────────────────────────────────


class Builder:
    """Drives the real service and records each exchange as a fixture."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.fixtures: List[Fixture] = []
        self._states: Dict[str, Dict[str, str]] = {}

    def state_ref(self, name: str, state: Dict[str, Any]) -> Dict[str, str]:
        """Reference a state, reusing an existing one when the content matches.

        Reuse matters: every edge-case resolve starts from the *same* round-one
        state, and writing it out eight times would triple the fixture size for no
        additional guarantee.
        """
        digest = state_digest(state)
        for existing_digest, ref in self._states.items():
            if existing_digest == digest:
                return ref
        ref = _write_state(name, state)
        self._states[digest] = ref
        return ref

    def call(
        self,
        name: str,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        state_name: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Perform one request, record it, and return the normalised response.

        ``state_name`` and any string values the caller marks are replaced by
        gzipped state references *inside the recorded copies only*; the live request
        always carries the full body.
        """
        response = self.client.request(method, path, json=body)
        recorded_request = self._with_state_refs(body, state_name)
        payload = normalise(response.json())
        recorded_response = self._reference_states_in_response(name, payload)
        self.fixtures.append(Fixture(
            name=name,
            method=method,
            path=path,
            status=response.status_code,
            request_body=recorded_request,
            response_body=recorded_response,
            notes=notes,
        ))
        return payload

    # State handling is explicit rather than automatic: a `state` key is the only
    # place a snapshot appears, so referencing it is a two-line rule instead of a
    # heuristic that could later mis-handle a new field.

    def _with_state_refs(
        self, body: Optional[Dict[str, Any]], state_name: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if body is None:
            return None
        out = dict(body)
        if state_name is not None and "state" in out:
            out["state"] = self.state_ref(state_name, out["state"])
        return out

    def _reference_states_in_response(self, name: str, payload: Any) -> Any:
        if isinstance(payload, dict) and isinstance(payload.get("state"), dict):
            out = dict(payload)
            out["state"] = self.state_ref(f"{name}-state", payload["state"])
            return out
        return payload


def build_fixtures() -> List[Fixture]:
    """Produce every fixture. Deterministic: same engine, same output, byte for byte."""
    from .app import app as fastapi_app

    client = TestClient(fastapi_app)
    builder = Builder(client)

    # ── static surfaces ──────────────────────────────────────────────────
    builder.call("01-health", "GET", "/v1/health",
                 notes="Version identity. A deploy that changes economics moves the digest.")
    builder.call("02-bundles-list", "GET", "/v1/bundles",
                 notes="Datasets a professor may choose. Note the absence of a seed.")
    builder.call("03-bundle-detail", "GET", "/v1/bundles/real605-fall26-v1",
                 notes="Operator view, including the seed and the integrity check.")

    # ── refusals before play ─────────────────────────────────────────────
    builder.call("04-create-unknown-bundle", "POST", "/v1/create-game-state",
                 body={"bundle_id": "does-not-exist", "teams": [{"team_id": "a", "team_name": "A"}]},
                 notes="An unknown bundle is an error, never a fallback to a default.")

    wrong_pool = [{
        "property_id": "OC-NOT-A-PROPERTY",
        "forecast": {"model_name": "bad", "predicted_fair_value": 10.0,
                     "predicted_noi_growth": 0.02, "probability_of_downside": 0.3},
        "policy": {"max_bid": 9.0, "target_ltv": 0.5},
    }]
    builder.call("05-create-mismatched-model", "POST", "/v1/create-game-state",
                 body={"bundle_id": "real605-fall26-v1", "teams": [
                     {"team_id": "a", "team_name": "A", "submissions": wrong_pool}]},
                 notes="Hard rejection. A model built for another dataset is refused, not warned about.")

    builder.call("06-create-duplicate-team-id", "POST", "/v1/create-game-state",
                 body={"bundle_id": "real605-fall26-v1", "teams": [
                     {"team_id": "a", "team_name": "A"},
                     {"team_id": "a", "team_name": "A again"}]},
                 notes="Two funds with one id would silently share a portfolio.")

    # ── game A: the round loop ───────────────────────────────────────────
    submissions = student_submissions()
    create_body = {
        "bundle_id": "real605-fall26-v1",
        "teams": [
            {"team_id": "student", "team_name": "REAL605 Student Fund", "submissions": submissions},
            {"team_id": "value", "team_name": "Value Fund"},
            {"team_id": "growth", "team_name": "Growth Fund"},
        ],
    }
    created = builder.call("07-create-initial-state", "POST", "/v1/create-game-state",
                           body=create_body,
                           notes="Practice round is open on one property; the scored pool is untouched.")
    state = created["state"]
    practice = created["public"]

    builder.call("08-open-round-too-early", "POST", "/v1/open-round",
                 body={"state": state}, state_name="07-create-initial-state",
                 notes="A round cannot be opened while one is open. Ordering is enforced.")

    practice_deal = practice["deals"][0]["property_id"]
    resolved_practice = builder.call(
        "09-resolve-practice-no-bids", "POST", "/v1/resolve-round",
        body={"state": state, "decisions": []}, state_name="07-create-initial-state",
        notes="Practice resolves with no decisions: the market moves, no fund transacts.",
    )
    state = resolved_practice["state"]

    builder.call("10-resolve-wrong-phase", "POST", "/v1/resolve-round",
                 body={"state": state, "decisions": []},
                 state_name="09-resolve-practice-no-bids-state",
                 notes="A resolved round cannot be resolved twice.")

    round1 = builder.call("11-open-round1", "POST", "/v1/open-round",
                          body={"state": state},
                          state_name="09-resolve-practice-no-bids-state",
                          notes="Round 1: four properties, and every reserve still hidden.")
    state = round1["state"]
    deals = [d["property_id"] for d in round1["public"]["deals"]]
    pool = _fresh_pool()

    # Four different failure and success modes in one round, which is why the
    # scored round offers four properties rather than one.
    decisions = []
    invalid_ltv = deals[0]
    decisions.append(_decision("student", invalid_ltv,
                               price=pool[invalid_ltv].asking_price * 1.02,
                               ltv=min(0.95, pool[invalid_ltv].max_ltv + 0.2)))
    heavy = deals[1]
    decisions.append(_decision("student", heavy, price=5000.0, ltv=0.6))
    below_reserve = deals[2]
    decisions.append(_decision("value", below_reserve,
                               price=pool[below_reserve].reserve_price * 0.90, ltv=0.5))
    win = deals[3]
    decisions.append(_decision("student", win,
                               price=pool[win].reserve_price * 1.03, ltv=0.55))
    resolved1 = builder.call(
        "12-resolve-round1", "POST", "/v1/resolve-round",
        body={"state": state, "decisions": decisions},
        state_name="11-open-round1-state",
        notes=(
            "One round, four outcomes: an over-levered bid refused, an unaffordable "
            "bid refused, a bid below the seller's reserve refused by the seller, "
            "and a valid bid that wins."
        ),
    )
    state = resolved1["state"]

    round2 = builder.call("13-open-round2", "POST", "/v1/open-round",
                          body={"state": state},
                          state_name="12-resolve-round1-state",
                          notes="Round 2, with round 1's purchases carried in the P&L bridge.")
    state = round2["state"]
    deals2 = [d["property_id"] for d in round2["public"]["deals"]]

    # Tie-breaks and competition.
    tie_ltv, tie_exact, contested, override_deal = deals2
    tie_price = pool[tie_ltv].reserve_price * 1.02
    decisions2 = [
        _decision("student", tie_ltv, price=tie_price, ltv=0.60),
        _decision("value", tie_ltv, price=tie_price, ltv=0.50),
        _decision("student", tie_exact, price=pool[tie_exact].reserve_price * 1.02, ltv=0.55),
        _decision("value", tie_exact, price=pool[tie_exact].reserve_price * 1.02, ltv=0.55),
        _decision("student", contested, price=pool[contested].reserve_price * 1.02, ltv=0.55),
        _decision("value", contested, price=pool[contested].reserve_price * 1.03, ltv=0.55),
        _decision("growth", contested, price=pool[contested].reserve_price * 1.05, ltv=0.55),
        _decision("student", override_deal,
                  price=max(policy_of(submissions, override_deal)["max_bid"] * 1.06,
                            pool[override_deal].reserve_price * 1.02),
                  ltv=0.55),
    ]
    resolved2 = builder.call(
        "14-resolve-round2", "POST", "/v1/resolve-round",
        body={"state": state, "decisions": decisions2},
        state_name="13-open-round2-state",
        notes=(
            "Price tie broken by lower leverage; an identical price AND leverage "
            "settled by the seeded draw; three funds contesting one property; and a "
            "bid deliberately above the team's own policy ceiling."
        ),
    )
    state = resolved2["state"]

    round3 = builder.call("15-open-round3", "POST", "/v1/open-round",
                          body={"state": state},
                          state_name="14-resolve-round2-state")
    state = round3["state"]
    deals3 = [d["property_id"] for d in round3["public"]["deals"]]
    decisions3 = [
        _decision("student", deals3[0], price=pool[deals3[0]].reserve_price * 1.02, ltv=0.60),
        _decision("student", deals3[1], price=pool[deals3[1]].reserve_price * 1.01, ltv=0.60),
        _decision("value", deals3[2], price=pool[deals3[2]].reserve_price * 1.04, ltv=0.60),
        # deals3[3] is left with no bid, so it goes unsold.
    ]
    resolved3 = builder.call(
        "16-resolve-round3", "POST", "/v1/resolve-round",
        body={"state": state, "decisions": decisions3},
        state_name="15-open-round3-state",
        notes="Three rounds of holdings: the bridge now shows income, interest and reserves.",
    )
    state = resolved3["state"]

    round4 = builder.call("17-open-round4", "POST", "/v1/open-round",
                          body={"state": state},
                          state_name="16-resolve-round3-state")
    state = round4["state"]
    deals4 = [d["property_id"] for d in round4["public"]["deals"]]
    decisions4 = []
    for index, property_id in enumerate(deals4):
        decisions4.append(_decision("student", property_id,
                                    price=pool[property_id].reserve_price * 1.02, ltv=0.60))
        decisions4.append(_decision("value", property_id,
                                    price=pool[property_id].reserve_price * 1.01, ltv=0.55))
    resolved4 = builder.call(
        "18-resolve-round4", "POST", "/v1/resolve-round",
        body={"state": state, "decisions": decisions4},
        state_name="17-open-round4-state",
        notes="Final scored round. Equity is now the binding constraint for some funds.",
    )
    state = resolved4["state"]

    # The completed state: `19-open-after-final` is what flips the game to complete,
    # so the debrief fixtures must start from its *response*, not from the state
    # before it. Passing the pre-completion state would freeze a debrief that says
    # the game is still running.
    after_final = builder.call("19-open-after-final", "POST", "/v1/open-round",
                               body={"state": state},
                               state_name="18-resolve-round4-state",
                               notes="Past the last round, opening reports completion instead of erroring.")
    assert after_final["game_complete"] is True
    state = after_final["state"]

    builder.call("20-team-view-student", "POST", "/v1/team-view",
                 body={"state": state, "team_id": "student"},
                 state_name="19-open-after-final-state",
                 notes="One fund's own forecast, policy, book and overrides -- and nobody else's.")

    builder.call("21-finalize-game", "POST", "/v1/finalize-game",
                 body={"state": state}, state_name="19-open-after-final-state",
                 notes="Standings, the analytics board, and the ten answers, from history alone.")
    builder.call("22-finalize-idempotent", "POST", "/v1/finalize-game",
                 body={"state": state}, state_name="19-open-after-final-state",
                 notes="Finalising is a view, not a step: the second call returns the "
                       "same state and the same debrief as the first.")

    # ── game B: boundaries and refusals, all from one open round ─────────
    edge = builder.call("23-create-edge-game", "POST", "/v1/create-game-state",
                        body={"bundle_id": "real605-fall26-v1", "teams": [
                            {"team_id": "alpha", "team_name": "Alpha Fund",
                             "submissions": submissions},
                            {"team_id": "beta", "team_name": "Beta Fund"}]},
                        notes="A second session on the same bundle, for boundary cases.")
    edge_state = edge["state"]
    edge_practice = builder.call("24-edge-resolve-practice", "POST", "/v1/resolve-round",
                                 body={"state": edge_state, "decisions": []},
                                 state_name="23-create-edge-game-state")
    edge_state = edge_practice["state"]
    edge_round = builder.call("25-edge-open-round1", "POST", "/v1/open-round",
                              body={"state": edge_state},
                              state_name="24-edge-resolve-practice-state",
                              notes="Every remaining edge case resolves from THIS state.")
    edge_state = edge_round["state"]
    edge_deals = [d["property_id"] for d in edge_round["public"]["deals"]]
    edge_snapshot = edge_state
    edge_name = "25-edge-open-round1-state"

    def edge_case(name: str, decisions: List[Dict[str, Any]], notes: str) -> None:
        builder.call(name, "POST", "/v1/resolve-round",
                     body={"state": edge_snapshot, "decisions": decisions},
                     state_name=edge_name, notes=notes)

    at_reserve = edge_deals[0]
    edge_case(
        "26-edge-bid-at-exact-reserve",
        [_decision("alpha", at_reserve, price=pool[at_reserve].reserve_price,
                   ltv=0.55, exact=True)],
        "A bid at exactly the reserve sells. The boundary is inclusive, so a tie "
        "against the seller's floor is not silently treated as a loss.",
    )
    edge_case(
        "27-edge-bid-just-below-reserve",
        [_decision("alpha", at_reserve, price=pool[at_reserve].reserve_price - 0.001,
                   ltv=0.55, exact=True)],
        "A thousand dollars below the reserve does not. Together with 26 this pins "
        "the boundary from both sides.",
    )
    edge_case(
        "28-edge-ltv-at-max",
        [_decision("alpha", at_reserve, price=pool[at_reserve].reserve_price * 1.02,
                   ltv=pool[at_reserve].max_ltv)],
        "Leverage at the property's ceiling is legal.",
    )
    edge_case(
        "29-edge-ltv-above-max",
        [_decision("alpha", at_reserve, price=pool[at_reserve].reserve_price * 1.02,
                   ltv=min(0.95, pool[at_reserve].max_ltv + 0.01))],
        "Leverage one notch above the ceiling is refused, and refused legibly.",
    )
    edge_case(
        "30-edge-duplicate-decision",
        [_decision("alpha", at_reserve, price=pool[at_reserve].reserve_price * 1.02, ltv=0.55),
         _decision("alpha", at_reserve, price=pool[at_reserve].reserve_price * 1.03, ltv=0.55)],
        "Two bids from one fund for one property: the second is rejected, not silently merged.",
    )
    edge_case(
        "31-edge-unknown-team",
        [_decision("nobody", at_reserve, price=pool[at_reserve].reserve_price * 1.02, ltv=0.55)],
        "A bid from a fund that is not in the game is reported, not crashed on.",
    )
    edge_case(
        "32-edge-bid-without-price",
        [{"team_id": "alpha", "property_id": at_reserve, "action": "BID"}],
        "A BID missing its price is refused: an incomplete decision is not a pass.",
    )
    edge_case(
        "33-edge-no-decisions",
        [],
        "Nobody bids on anything: no sales, no error, the market still moves.",
    )
    identical = edge_deals[1]
    edge_case(
        "34-edge-identical-bid-and-ltv",
        [_decision("alpha", identical, price=pool[identical].reserve_price * 1.02, ltv=0.55),
         _decision("beta", identical, price=pool[identical].reserve_price * 1.02, ltv=0.55)],
        "Identical price and identical leverage: settled by the seeded draw, so the "
        "result is reproducible rather than arbitrary.",
    )
    return builder.fixtures


def _decision(
    team_id: str,
    property_id: str,
    price: float,
    ltv: float,
    exact: bool = False,
) -> Dict[str, Any]:
    """A BID, rounded to six decimals to match the engine's own convention.

    ``exact=True`` skips the rounding and is required whenever the *boundary* is
    the point of the fixture. Rounding a bid aimed at the seller's reserve to four
    decimals silently moves it below the reserve, which would turn "a bid at the
    reserve sells" into a fixture asserting the opposite behaviour for the wrong
    reason -- a test that passes while proving nothing.
    """
    return {
        "team_id": team_id,
        "property_id": property_id,
        "action": "BID",
        "bid": price if exact else round(price, 6),
        "ltv": round(ltv, 6),
    }


# ── writing ───────────────────────────────────────────────────────────────


def write_fixtures(verbose: bool = False) -> int:
    """Regenerate `tests/contracts/engine_api/`. Removes stale files first.

    The clean happens *before* building, not after: building writes the gzipped
    states as a side effect, so clearing afterwards would delete the very files the
    fixtures refer to.
    """
    if CONTRACT_DIR.exists():
        import shutil

        shutil.rmtree(CONTRACT_DIR)
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = build_fixtures()

    index = {
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "generated_from": "service/engine_api (the verified Python engine)",
        "normalisation": {
            "timestamps": "event_log[*].at replaced with a constant",
            "engine_state": "stored once under _states/ as gzipped canonical JSON, "
                            "referenced by sha256",
        },
        "fixtures": [],
    }

    for fixture in fixtures:
        directory = CONTRACT_DIR / fixture.name
        directory.mkdir(parents=True, exist_ok=True)
        request = {
            "method": fixture.method,
            "path": fixture.path,
            "expected_status": fixture.status,
            "body": fixture.request_body,
        }
        (directory / "request.json").write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n"
        )
        (directory / "response.json").write_text(
            json.dumps(fixture.response_body, indent=2, sort_keys=True) + "\n"
        )
        index["fixtures"].append({
            "name": fixture.name,
            "method": fixture.method,
            "path": fixture.path,
            "expected_status": fixture.status,
            "notes": fixture.notes,
        })
        if verbose:
            print(f"  {fixture.name}  {fixture.method} {fixture.path} -> {fixture.status}")

    (CONTRACT_DIR / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n"
    )
    return len(fixtures)
