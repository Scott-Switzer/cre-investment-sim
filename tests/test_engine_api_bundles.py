"""
Versioned datasets.

A student's model is trained against one property pool. Change the seed and the
property ids stay the same while the buildings behind them change, so the model
keeps producing confident numbers about the wrong things -- silently, five minutes
into a class. `scripts/verify_student_override.py` found this the hard way: a
hand-built model reported $0.83M average error on the seed it was built for and
$8.38M on another.

So the rule is structural rather than advisory:

* a session selects a **bundle**, and there is no seed parameter to abuse;
* a bundle records the digest of the economics and of the pool it was built against;
* a submission that does not match the bundle's pool is **rejected before play**,
  not warned about.

The tests below check each of those, plus the one that matters most: that the
integrity check can actually fail.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from service.engine_api import bundles
from service.engine_api.app import app
from service.engine_api.bundles import BundleError, GameBundle


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def bundle() -> GameBundle:
    return bundles.load_bundle("real605-fall26-v1")


# ── the bundle exists and describes the live engine ───────────────────────


def test_the_published_bundle_loads(bundle: GameBundle):
    assert bundle.bundle_id == "real605-fall26-v1"
    assert bundle.display_name
    assert bundle.schema_version == bundles.BUNDLE_SCHEMA_VERSION
    assert bundle.packet_version


def test_the_published_bundle_matches_the_live_engine(bundle: GameBundle):
    """If this fails, the economics or the pool changed and the bundle is stale.

    That is the tripwire the project needed: a coefficient edit now fails a test
    instead of quietly invalidating every student's pre-built model.
    """
    ok, message = bundles.verify_bundle_integrity(bundle)
    assert ok, message


def test_economics_digest_is_stable_across_calls():
    assert bundles.economics_digest() == bundles.economics_digest()


def test_economics_digest_changes_when_a_coefficient_changes(monkeypatch):
    """Proves the digest is a real check rather than a constant.

    Without this, `verify_bundle_integrity` could pass because nothing it looks at
    ever moves.
    """
    import src.game.adjudicator as adjudicator

    before = bundles.economics_digest()
    monkeypatch.setattr(adjudicator, "ACQUISITION_COST_RATE", 0.025)
    assert bundles.economics_digest() != before


def test_a_stale_economics_digest_fails_the_integrity_check(bundle: GameBundle):
    stale = dataclasses.replace(bundle, economics_digest="0" * 64)
    ok, message = bundles.verify_bundle_integrity(stale)
    assert ok is False
    assert "economic coefficients have changed" in message


def test_a_stale_pool_hash_fails_the_integrity_check(bundle: GameBundle):
    stale = dataclasses.replace(bundle, candidate_pool_hash="0" * 64)
    ok, message = bundles.verify_bundle_integrity(stale)
    assert ok is False
    assert "property pool" in message


# ── the pool hash means something ─────────────────────────────────────────


def test_pool_hash_is_deterministic():
    assert bundles.pool_hash_for_seed(bundles.PUBLISHED_SEED) == \
        bundles.pool_hash_for_seed(bundles.PUBLISHED_SEED)


def test_pool_hash_differs_for_a_different_seed():
    """If it did not, the hash could not detect anything."""
    assert bundles.pool_hash_for_seed(bundles.PUBLISHED_SEED) != \
        bundles.pool_hash_for_seed(bundles.PUBLISHED_SEED + 1)


def test_pool_hash_covers_the_fields_a_model_is_trained_on():
    """The hash must move when a decision-relevant field moves.

    A hash over property ids alone would be stable across exactly the change this
    whole mechanism exists to catch.
    """
    for field in ("asking_price", "current_noi", "occupancy", "building_sf",
                  "max_ltv", "debt_rate"):
        assert field in bundles.POOL_HASH_FIELDS, field


# ── the seed is not a choice ──────────────────────────────────────────────


def test_arbitrary_seeds_are_refused():
    with pytest.raises(BundleError, match="not the published dataset seed"):
        bundles.require_published_seed(bundles.PUBLISHED_SEED + 1)


def test_the_published_seed_is_accepted():
    bundles.require_published_seed(bundles.PUBLISHED_SEED)


def test_unknown_bundle_is_an_error_with_no_default(bundle: GameBundle):
    with pytest.raises(BundleError, match="unknown bundle"):
        bundles.load_bundle("nope")


def test_bundle_json_carries_no_surprise_keys():
    """The bundle file is small and reviewable; this keeps it that way."""
    path = bundles.BUNDLE_DIR / "real605-fall26-v1.json"
    payload = json.loads(path.read_text())
    assert set(payload) == {
        "bundle_id", "display_name", "engine_version", "economics_version",
        "economics_digest", "packet_version", "seed", "candidate_pool_hash",
        "schema_version", "description",
    }


def test_the_seed_lives_in_system_metadata_and_is_not_advertised(client: TestClient):
    """`/v1/bundles` is what a professor screen reads: no seed, no hashes."""
    listed = client.get("/v1/bundles").json()["bundles"]
    assert listed
    summary = listed[0]
    assert set(summary) == {
        "bundle_id", "display_name", "packet_version", "economics_version", "description"
    }


# ── a mismatched model is rejected before play, not warned about ──────────


def test_a_model_for_another_pool_is_hard_rejected(client: TestClient):
    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{
            "team_id": "mismatched",
            "team_name": "Mismatched Fund",
            "submissions": [{
                "property_id": "OC-NOT-A-PROPERTY",
                "forecast": {"predicted_fair_value": 10.0, "predicted_noi_growth": 0.02},
                "policy": {"max_bid": 9.0, "target_ltv": 0.5},
            }],
        }],
    })
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "different property dataset" in detail
    # The message has to tell the student what to do, not merely that they failed.
    assert "Download the correct" in detail


def test_a_partial_model_is_rejected_too(client: TestClient):
    """Covering half the pool is not "close enough" -- it is a different dataset."""
    from service.engine_api.fixtures import student_submissions

    partial = student_submissions()[:10]
    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{"team_id": "partial", "team_name": "Partial", "submissions": partial}],
    })
    assert response.status_code == 409
    assert "110 properties missing" in response.json()["detail"]


def test_a_complete_model_is_accepted(client: TestClient):
    from service.engine_api.fixtures import student_submissions

    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{"team_id": "ok", "team_name": "OK", "submissions": student_submissions()}],
    })
    assert response.status_code == 200, response.text


def test_a_fund_may_play_with_no_model_at_all(client: TestClient):
    """No model is a valid seat: the bot funds play this way, and it is honest.

    An absent model means "no view", which is different from a wrong one and must
    not be rejected as a mismatch.
    """
    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{"team_id": "bot", "team_name": "Bot Fund"}],
    })
    assert response.status_code == 200


def test_a_stale_bundle_refuses_to_start_a_game(client: TestClient, monkeypatch):
    """A game must not begin against economics the bundle did not freeze.

    Reported as a server fault rather than bad input: the caller sent a valid bundle
    id, and no amount of retrying will fix a dataset that no longer matches the code.
    """
    stale = dataclasses.replace(bundles.load_bundle("real605-fall26-v1"),
                                economics_digest="0" * 64)
    monkeypatch.setattr(bundles, "load_bundle", lambda _bundle_id: stale)
    response = client.post("/v1/create-game-state", json={
        "bundle_id": "real605-fall26-v1",
        "teams": [{"team_id": "a", "team_name": "A"}],
    })
    assert response.status_code == 500
    assert response.json()["error"] == "bundle_integrity"
    assert "integrity check" in response.json()["detail"]
