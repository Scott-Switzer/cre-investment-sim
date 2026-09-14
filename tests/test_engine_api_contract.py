"""
The engine service's executable contract.

Two layers, deliberately separate:

1. **Replay** — every recorded request is replayed against the live service and the
   full response must match, byte for byte, including the engine state. This proves
   the contract still holds; it does not say what the contract *means*.
2. **Semantics** — a smaller set of assertions about what actually happened in those
   fixtures: which reserve was met, which tie was broken how, which bid was refused
   and why. A replay test passes just as happily against nonsense as against correct
   behaviour, so the meaning has to be asserted explicitly somewhere.

The semantics below were read off the generated fixtures and then written down. If
the engine's behaviour changes, the replay fails loudly first; if the *meaning*
changes while the bytes change consistently, these catch it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.engine_api import bundles, fixtures, public, serde
from service.engine_api.app import app

CONTRACT_DIR = fixtures.CONTRACT_DIR
INDEX = json.loads((CONTRACT_DIR / "index.json").read_text())
FIXTURE_NAMES = [entry["name"] for entry in INDEX["fixtures"]]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _load(name: str) -> tuple[dict, dict]:
    directory = CONTRACT_DIR / name
    request = json.loads((directory / "request.json").read_text())
    response = json.loads((directory / "response.json").read_text())
    return request, response


def _materialise(body, contract_dir: Path = CONTRACT_DIR):
    """Swap any `$state_ref` placeholders for the state they point at."""
    if fixtures.is_state_ref(body):
        return fixtures.read_state(contract_dir, body)
    if isinstance(body, dict):
        return {k: _materialise(v, contract_dir) for k, v in body.items()}
    if isinstance(body, list):
        return [_materialise(v, contract_dir) for v in body]
    return body


def _align_state_refs(actual, expected):
    """Replace an actual engine state with the reference form the fixture records.

    The state is still compared in full -- the digest is taken from what the
    service returned, and the fixture's own digest is part of the equality below.
    Only the bulky encoding is shared.
    """
    if isinstance(expected, dict) and fixtures.is_state_ref(expected):
        return {
            fixtures.STATE_REF_KEY: expected[fixtures.STATE_REF_KEY],
            "sha256": fixtures.state_digest(actual),
        }
    if isinstance(expected, dict) and isinstance(actual, dict):
        return {k: _align_state_refs(actual.get(k), v) for k, v in expected.items()}
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [_align_state_refs(a, e) for a, e in zip(actual, expected)]
    return actual


# ── 1. replay ─────────────────────────────────────────────────────────────


def test_fixture_index_is_complete():
    """The suite must not silently shrink: a lost fixture is a lost guarantee."""
    assert INDEX["fixture_schema_version"] == fixtures.FIXTURE_SCHEMA_VERSION
    assert len(FIXTURE_NAMES) >= 25, f"only {len(FIXTURE_NAMES)} fixtures"
    for name in FIXTURE_NAMES:
        assert (CONTRACT_DIR / name / "request.json").exists(), name
        assert (CONTRACT_DIR / name / "response.json").exists(), name


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_replays_byte_for_byte(name: str, client: TestClient):
    request, expected = _load(name)
    body = _materialise(request["body"])
    response = client.request(request["method"], request["path"], json=body)

    assert response.status_code == request["expected_status"], (
        f"{name}: expected {request['expected_status']}, got {response.status_code}: "
        f"{response.text[:400]}"
    )
    actual = fixtures.normalise(response.json())
    assert _align_state_refs(actual, expected) == expected, (
        f"{name}: response differs from the frozen contract"
    )


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_is_deterministic(name: str, client: TestClient):
    """Same request twice, same bytes. The service holds no session state."""
    request, _ = _load(name)
    body = _materialise(request["body"])
    first = client.request(request["method"], request["path"], json=body)
    second = client.request(request["method"], request["path"], json=body)
    assert fixtures.canonical_digest(fixtures.normalise(first.json())) == \
        fixtures.canonical_digest(fixtures.normalise(second.json()))


def test_state_references_are_verifiable():
    """A state file whose digest does not match its reference must be rejected."""
    request, _ = _load("11-open-round1")
    reference = dict(request["body"]["state"])
    reference["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        fixtures.read_state(CONTRACT_DIR, reference)


# ── 2. semantics ──────────────────────────────────────────────────────────
#
# Read these as the specification of the auction, written in the form of the
# outcomes the engine actually produced.


def _response(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name / "response.json").read_text())


def test_bundle_pool_covers_every_candidate_and_matches_its_bundle():
    """The pool the game service validates a model against is the pool the
    bundle pins -- recomputed live, not read back from the bundle file."""
    response = _response("03b-bundle-pool")
    assert response["pool_count"] == 120
    assert response["candidate_pool_hash"] == response["bundle"]["candidate_pool_hash"]
    ids = [prop["property_id"] for prop in response["properties"]]
    assert len(ids) == 120
    assert len(set(ids)) == 120, "the pool contains a duplicate property id"


def test_bundle_pool_uses_the_same_property_dto_as_the_round_loop():
    """One representation of a building (risk R5).

    If the check-in screen and the deal card could disagree about the same
    property, a student would be told their model is fine for a building they are
    then shown a different version of.
    """
    pool = _response("03b-bundle-pool")["properties"]
    round_one = _response("11-open-round1")["public"]["deals"]
    by_id = {prop["property_id"]: prop for prop in pool}
    assert round_one, "round one offered no deals"
    for deal in round_one:
        assert deal == by_id[deal["property_id"]], (
            f"{deal['property_id']} is represented differently in the pool than "
            "in the round"
        )


def test_bundle_pool_is_refused_for_an_unknown_bundle():
    assert _response("03c-bundle-pool-unknown")["error"] == "bundle"


def _auction(name: str, property_id: str) -> dict:
    for auction in _response(name)["public_results"]["auctions"]:
        if auction["property_id"] == property_id:
            return auction
    raise AssertionError(f"{property_id} missing from {name}")


def _decision(name: str, index: int = 0) -> dict:
    request, _ = _load(name)
    return request["body"]["decisions"][index]


def test_health_reports_frozen_versions():
    body = _response("01-health")
    assert body["status"] == "ok"
    assert body["game"] == "cre-investment-committee"
    assert body["schema_version"] == bundles.BUNDLE_SCHEMA_VERSION
    assert body["serde_schema_version"] == serde.SERDE_SCHEMA_VERSION
    assert body["economics_digest"] == bundles.economics_digest()


def test_bundle_list_does_not_expose_a_seed(client: TestClient):
    """A professor selects a dataset. The seed is not a choice they can make."""
    listed = client.get("/v1/bundles").json()["bundles"]
    assert listed, "no bundles installed"
    for bundle in listed:
        assert "seed" not in bundle
        assert "engine_seed" not in bundle
    detail = client.get(f"/v1/bundles/{listed[0]['bundle_id']}").json()
    assert detail["integrity_ok"] is True
    assert isinstance(detail["seed"], int)


def test_create_has_no_seed_parameter(client: TestClient):
    """The create request forbids unknown fields, so a seed cannot even be sent."""
    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{"team_id": "a", "team_name": "A"}],
        "seed": 1,
    })
    assert response.status_code == 422


def test_unknown_bundle_is_refused_not_defaulted():
    body = _response("04-create-unknown-bundle")
    assert body["error"] == "bundle"
    assert "real605-fall26-v1" in body["detail"]


def test_mismatched_model_is_hard_rejected_before_play():
    body = _response("05-create-mismatched-model")
    assert body["error"] == "illegal_operation"
    assert "does not match this dataset" in body["detail"]
    assert "different property dataset" in body["detail"]


def test_duplicate_team_id_is_refused():
    assert "duplicate team_id" in _response("06-create-duplicate-team-id")["detail"]


def test_round_ordering_is_enforced():
    assert "cannot open a round" in _response("08-open-round-too-early")["detail"]
    assert "cannot resolve" in _response("10-resolve-wrong-phase")["detail"]


def test_practice_round_offers_one_property_and_grades_nothing():
    """Practice is for learning the interface; it must not move a fund's standing."""
    request, _ = _load("07-create-initial-state")
    created_state = _materialise(request["body"]["state"]) if False else None  # noqa: F841
    practice = json.loads((CONTRACT_DIR / "07-create-initial-state" / "response.json").read_text())["public"]
    assert practice["round_number"] == -1
    assert practice["is_practice"] is True
    assert practice["stage"] == "PRACTICE"
    assert len(practice["deals"]) == 1

    resolved = _response("09-resolve-practice-no-bids")
    assert resolved["public_results"]["round_number"] == -1
    for entry in resolved["public_results"]["pnl"]:
        assert entry["assets"] == 0
        assert entry["nav"] == pytest.approx(100.0)


def test_round_one_offers_four_properties():
    body = _response("11-open-round1")
    assert body["public"]["round_number"] == 0
    assert body["public"]["stage"] == "ROUND 1"
    assert len(body["public"]["deals"]) == 4


def test_over_levered_bid_is_refused_legibly():
    property_id = _decision("12-resolve-round1", 0)["property_id"]
    assert not _auction("12-resolve-round1", property_id)["sold"]
    rejection = _response("12-resolve-round1")["rejected_decisions"][0]
    assert rejection["property_id"] == property_id
    assert "LTV" in rejection["reason"]


def test_unaffordable_bid_is_refused_legibly():
    property_id = _decision("12-resolve-round1", 1)["property_id"]
    assert not _auction("12-resolve-round1", property_id)["sold"]
    rejection = _response("12-resolve-round1")["rejected_decisions"][1]
    assert rejection["property_id"] == property_id
    assert "Insufficient cash" in rejection["reason"]


def test_bid_below_reserve_does_not_sell():
    """The seller is a participant with a floor, not a formality."""
    property_id = _decision("12-resolve-round1", 2)["property_id"]
    auction = _auction("12-resolve-round1", property_id)
    assert auction["sold"] is False
    assert "below reserve" in auction["reason"]


def test_valid_bid_above_reserve_wins():
    property_id = _decision("12-resolve-round1", 3)["property_id"]
    auction = _auction("12-resolve-round1", property_id)
    assert auction["sold"] is True
    assert auction["winning_team_id"] == "student"
    assert auction["winning_bid"] > auction["reserve_price"]


def test_price_tie_is_broken_by_lower_leverage():
    """Same price, less debt wins: the seller is buying certainty, not just price."""
    name = "14-resolve-round2"
    property_id = _decision(name, 0)["property_id"]
    student = _decision(name, 0)
    value = _decision(name, 1)
    assert student["bid"] == value["bid"], "fixture no longer constructs a price tie"
    assert value["ltv"] < student["ltv"]
    auction = _auction(name, property_id)
    assert auction["winning_team_id"] == "value"


def test_identical_price_and_leverage_uses_the_seeded_draw():
    """A perfect tie must still resolve reproducibly, not arbitrarily."""
    name = "34-edge-identical-bid-and-ltv"
    request, _ = _load(name)
    decisions = request["body"]["decisions"]
    assert decisions[0]["bid"] == decisions[1]["bid"]
    assert decisions[0]["ltv"] == decisions[1]["ltv"]
    property_id = decisions[0]["property_id"]
    auction = _auction(name, property_id)
    assert auction["sold"] is True
    assert auction["winning_team_id"] in {"alpha", "beta"}


def test_three_funds_contesting_one_property_goes_to_the_highest_bid():
    name = "14-resolve-round2"
    property_id = _decision(name, 4)["property_id"]
    bids = {
        d["team_id"]: d["bid"]
        for d in _load(name)[0]["body"]["decisions"]
        if d["property_id"] == property_id
    }
    auction = _auction(name, property_id)
    assert len(bids) == 3
    assert auction["winning_team_id"] == max(bids, key=bids.get)


def test_a_bid_above_the_teams_own_ceiling_is_recorded_as_an_override():
    team_view = _response("20-team-view-student")
    overrides = team_view["overrides"]
    assert overrides, "no overrides recorded"
    above = [o for o in overrides if o["bid_override"] > 0]
    assert above, "the deliberate above-policy bid was not recorded"
    for override in overrides:
        assert override["bid_override"] == pytest.approx(
            override["actual_bid"] - override["model_max_bid"], abs=1e-6
        )
        assert override["ltv_override"] == pytest.approx(
            override["actual_ltv"] - override["model_target_ltv"], abs=1e-6
        )


def test_exact_reserve_boundary_is_inclusive_and_pinned_from_both_sides():
    at_reserve = _auction("26-edge-bid-at-exact-reserve", _decision("26-edge-bid-at-exact-reserve")["property_id"])
    below = _auction("27-edge-bid-just-below-reserve", _decision("27-edge-bid-just-below-reserve")["property_id"])
    assert at_reserve["sold"] is True
    assert at_reserve["winning_bid"] == at_reserve["reserve_price"]
    assert below["sold"] is False
    assert below["reserve_price"] == at_reserve["reserve_price"]


def test_leverage_ceiling_is_inclusive():
    at_max = _auction("28-edge-ltv-at-max", _decision("28-edge-ltv-at-max")["property_id"])
    above = _response("29-edge-ltv-above-max")
    assert at_max["sold"] is True
    assert above["rejected_decisions"], "a bid above the property's LTV cap was accepted"
    assert "LTV" in above["rejected_decisions"][0]["reason"]


def test_illegal_decisions_are_reported_rather_than_crashing():
    """A student's mistake is teaching material, not a server fault."""
    reasons = {
        "30-edge-duplicate-decision": "Already submitted",
        "31-edge-unknown-team": "unknown team",
        "32-edge-bid-without-price": "requires both a price and an LTV",
    }
    for name, expected in reasons.items():
        body = _response(name)
        assert body["rejected_decisions"], name
        assert expected in body["rejected_decisions"][0]["reason"], name
        # The round still resolves: a bad decision does not stall the class.
        assert "public_results" in body


def test_no_bids_means_nothing_sells():
    body = _response("33-edge-no-decisions")
    assert body["rejected_decisions"] == []
    assert all(auction["sold"] is False for auction in body["public_results"]["auctions"])


def test_final_round_completes_and_opening_after_it_reports_completion():
    completed = _response("18-resolve-round4")
    assert completed["public_results"]["round_number"] == 3
    after = _response("19-open-after-final")
    assert after["game_complete"] is True
    assert after["public"]["stage"] == "DEBRIEF"


def test_finalize_is_read_only_and_idempotent():
    first = _response("21-finalize-game")
    second = _response("22-finalize-idempotent")
    assert first["standings"] == second["standings"]
    assert first["debrief"] == second["debrief"]
    assert first["game_complete"] is True
    # The state reference is shared, so the two calls returned the same state and
    # the digest check below covers it. A debrief that mutated anything would fail
    # here even if its own answer text happened to match.
    assert first["state"] == second["state"]


def test_debrief_answers_all_ten_questions_from_recorded_history():
    debrief = _response("21-finalize-game")["debrief"]
    assert _response("21-finalize-game")["game_complete"] is True
    assert len(debrief["answers"]) == 10
    for answer in debrief["answers"]:
        assert answer["question"]
        assert answer["answer"], f"question {answer['number']} has no answer"
    assert "channels" in debrief
    assert "override_summary" in debrief


def test_analysis_and_outcome_are_judged_separately_on_the_only_evidence_available():
    """A good decision with a bad outcome must be representable.

    If every bad outcome implied a bad decision, the distinction this course is
    built on (model / manager / luck) could never be taught.
    """
    body = _response("18-resolve-round4")
    channels = {entry["team_id"]: entry for entry in body["public_results"]["pnl"]}
    assert channels, "no channel data"
    for entry in channels.values():
        assert set(entry) >= {
            "value_channel", "noi_income", "interest_paid",
            "acquisition_costs", "reserves", "nav",
        }

    # Every recorded attempt in the finished game carries all three labels, which
    # is what lets the debrief separate a weak model from a weak decision from luck.
    debrief = _response("21-finalize-game")["debrief"]
    assert debrief["case_counts"], "no attempt cases were classified"
    for example in debrief["examples"].values():
        assert example["model_label"] in {"GOOD_MODEL", "WEAK_MODEL"}
        assert example["decision_label"] in {"GOOD_DECISION", "BAD_DECISION"}
        assert example["outcome_label"] in {"GOOD_OUTCOME", "BAD_OUTCOME"}
        assert example["override_label"] in {
            "DISCIPLINED", "OVERRODE_UP", "OVERRODE_DOWN", "NO_BID"
        }
        assert example["case_labels"]
        assert example["headline"]

    # At least one attempt where the decision was sound and the year was not. This
    # is the case the whole exercise exists to make visible, and a fixture set that
    # never produces it is a fixture set that cannot demonstrate the lesson.
    assert "GOOD DECISION + BAD REALIZED OUTCOME" in debrief["case_counts"]

    # And the override lesson: deviating from your own stated ceiling must be able
    # to cost money, or "follow your model" is advice the game never tests.
    summary = debrief["override_summary"]
    assert summary["overridden_count"] > 0
    assert summary["disciplined_count"] > 0
    assert summary["overridden_avg_return"] < summary["disciplined_avg_return"], (
        "overrides were not punished in this seed, so the game cannot teach why "
        "discipline matters"
    )


# ── 3. the five-channel NAV identity, over HTTP ───────────────────────────


def test_five_channel_nav_identity_holds_at_every_scored_resolution():
    """NAV - starting equity == value + NOI - interest - costs - reserves.

    This is the whole CRE teaching object, so it is checked at every round of the
    scripted game rather than only at the end, and it is checked on the numbers the
    API actually publishes rather than on engine internals.
    """
    starting_equity = 100.0
    for name in ("12-resolve-round1", "14-resolve-round2", "16-resolve-round3", "18-resolve-round4"):
        body = _response(name)
        for entry in body["public_results"]["pnl"]:
            explained = (
                entry["value_channel"]
                + entry["noi_income"]
                - entry["interest_paid"]
                - entry["acquisition_costs"]
                - entry["reserves"]
            )
            assert entry["nav"] - starting_equity == pytest.approx(explained, abs=1e-4), (
                f"{name}/{entry['team_id']}: channels do not explain NAV"
            )


def test_each_channel_actually_moves_over_a_four_round_game():
    """A channel that is always zero would satisfy the identity and teach nothing."""
    final = {entry["team_id"]: entry for entry in _response("18-resolve-round4")["public_results"]["pnl"]}
    student = final["student"]
    for channel in ("value_channel", "noi_income", "interest_paid",
                    "acquisition_costs", "reserves"):
        assert student[channel] != 0, f"{channel} never moved across four rounds"
    # Interest and rent are both live, and rent exceeds the cost of debt here --
    # which is the positive-carry assumption the whole exercise rests on.
    assert student["noi_income"] > student["interest_paid"]


def test_standings_match_the_channel_data():
    """The leaderboard must be the same numbers, ranked -- not a second calculation."""
    body = _response("21-finalize-game")
    by_nav = {entry["team_id"]: entry["nav"] for entry in body["debrief"]["channels"]}
    for row in body["standings"]:
        assert row["nav"] == pytest.approx(by_nav[row["team_id"]], abs=1e-6)
    navs = [row["nav"] for row in body["standings"]]
    assert navs == sorted(navs, reverse=True)
    assert [row["rank"] for row in body["standings"]] == list(range(1, len(navs) + 1))


def test_the_game_has_a_winner_and_losers_and_not_everyone_prospered():
    """A fixture where every fund wins would be a fixture that tests nothing."""
    standings = _response("21-finalize-game")["standings"]
    assert len(standings) >= 3
    assert standings[0]["nav"] > standings[-1]["nav"]


def test_public_round_payload_matches_the_service_projection():
    """The frozen fixture and a freshly restored game must agree.

    Rebuilds the game from the state the *response* carries and re-runs the
    projection. This is what proves the round payload is a pure function of state
    rather than something the request happened to carry -- and it guards against the
    fixtures drifting from the live projection while still replaying, which is
    possible if a fixture were ever hand-edited.
    """
    recorded = json.loads((CONTRACT_DIR / "11-open-round1" / "response.json").read_text())
    state = fixtures.read_state(CONTRACT_DIR, recorded["state"])
    game = serde.restore_game(state)
    assert public.public_round(game) == recorded["public"]
