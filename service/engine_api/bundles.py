"""
Versioned game bundles.

A student's model is trained against ONE property pool. The pool is generated
deterministically from a seed, and a different seed keeps the same property ids
while changing what those ids represent -- so a model built for one pool predicts
nonsense for another, silently, in class.

The rule that follows from this is the whole point of this module:

    A professor selects a DATASET, never a seed.

The raw seed is system metadata. It appears in the bundle file for engineers and
is never surfaced as a choice. A model submission is resolved against the session's
bundle and is HARD REJECTED if it does not match -- no warning, no coercion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from src.game.adjudicator import ACQUISITION_COST_RATE, BASE_CAP_RATE
from src.game.manager import GameConfig, GameManager

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "config" / "bundles"

# The bundle format itself. Bump when the JSON shape changes incompatibly.
BUNDLE_SCHEMA_VERSION = 1

# The seed the published student packet and the shipped fixture were built
# against. Sessions must use this; only demo/regeneration paths may vary it.
PUBLISHED_SEED = 20240331


class BundleError(RuntimeError):
    """Raised when a bundle is missing, malformed, or does not match a pool."""


class BundleIntegrityError(BundleError):
    """A bundle no longer describes the engine it claims to.

    Separated from the plain error because the two need different responses. An
    unknown bundle id is the caller's mistake and can be corrected by the caller.
    A bundle whose economics have drifted is a *deployment* problem: the caller did
    nothing wrong, retrying will not help, and every session on that dataset is
    unsafe until somebody redeploys. Reporting both as 400 would bury the one that
    needs a human.
    """


@dataclass(frozen=True)
class GameBundle:
    """One frozen, versioned dataset + economics pairing.

    ``candidate_pool_hash`` is the integrity check that makes "this model was built
    for a different dataset" a mechanical test rather than a judgement call.
    """

    bundle_id: str
    display_name: str
    engine_version: str
    economics_version: str
    economics_digest: str
    packet_version: str
    seed: int
    candidate_pool_hash: str
    schema_version: int
    description: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "display_name": self.display_name,
            "engine_version": self.engine_version,
            "economics_version": self.economics_version,
            "economics_digest": self.economics_digest,
            "packet_version": self.packet_version,
            "seed": self.seed,
            "candidate_pool_hash": self.candidate_pool_hash,
            "schema_version": self.schema_version,
            "description": self.description,
        }


# ── economics identity ────────────────────────────────────────────────────
#
# A digest over the frozen economic coefficients. It is recorded in each bundle
# and asserted by a test, so "the economics did not change" is checkable rather
# than asserted in prose. If a coefficient moves, the digest moves and the test
# fails loudly -- which is exactly the tripwire this project has needed.


def _economics_payload() -> Dict[str, object]:
    import src.game.adjudicator as adj

    return {
        "base_cap_rate": adj.BASE_CAP_RATE,
        "base_vacancy": adj.BASE_VACANCY,
        "base_rent_index": adj.BASE_RENT_INDEX,
        "base_macro": {
            "policy_rate": adj.BASE_POLICY_RATE,
            "unemployment": adj.BASE_UNEMPLOYMENT,
            "employment_growth": adj.BASE_EMPLOYMENT_GROWTH,
            "inflation": adj.BASE_INFLATION,
            "credit_conditions": adj.BASE_CREDIT_CONDITIONS,
        },
        "noi_growth": {
            "base": adj.NOI_GROWTH_BASE,
            "tight_bonus": adj.NOI_GROWTH_TIGHT_VACANCY_BONUS,
            "tight_threshold": adj.TIGHT_VACANCY_THRESHOLD,
            "sigma": adj.NOI_GROWTH_SIGMA,
            "min": adj.MIN_NOI_GROWTH,
            "max": adj.MAX_NOI_GROWTH,
        },
        "cap_rate": {
            "noise_sigma": adj.CAP_NOISE_SIGMA,
            "min": adj.MIN_CAP_RATE,
            "max": adj.MAX_CAP_RATE,
        },
        "acquisition_cost_rate": adj.ACQUISITION_COST_RATE,
        "capital_reserve_rate": adj.CAPITAL_RESERVE_RATE,
        "scenario_deltas": adj.SCENARIO_DELTAS,
    }


def economics_digest() -> str:
    """Stable digest of every frozen economic coefficient."""
    canon = json.dumps(_economics_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# ── pool identity ─────────────────────────────────────────────────────────

# The fields that define what a model was trained against. Anything a student
# could have used as a feature or a target belongs here.
POOL_HASH_FIELDS: Tuple[str, ...] = (
    "property_id",
    "asking_price",
    "current_noi",
    "current_cap",
    "occupancy",
    "building_sf",
    "year_built",
    "max_ltv",
    "debt_rate",
    "amortization_years",
)


def pool_fingerprint_rows(properties: Iterable[object]) -> List[Dict[str, object]]:
    rows = []
    for prop in properties:
        row = {}
        for field in POOL_HASH_FIELDS:
            value = getattr(prop, field, None)
            if isinstance(value, float):
                value = round(value, 6)
            row[field] = value
        rows.append(row)
    rows.sort(key=lambda r: str(r["property_id"]))
    return rows


def compute_candidate_pool_hash(properties: Iterable[object]) -> str:
    """Hash of the candidate pool a model must have been built against."""
    canon = json.dumps(
        pool_fingerprint_rows(properties), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode()).hexdigest()


def pool_hash_for_seed(seed: int, count: int = 120) -> str:
    """The pool hash for a fresh game at ``seed``.

    Uses the same construction the game itself uses, so the hash describes the
    pool a session will actually offer rather than an idealised one.
    """
    gm = GameManager(GameConfig(seed=seed, starting_equity=100.0, total_rounds=4,
                                properties_per_round=4, practice_round=True))
    return compute_candidate_pool_hash(list(gm.all_properties.values()))


# ── loading ───────────────────────────────────────────────────────────────

def _bundle_from_dict(data: Dict[str, object]) -> GameBundle:
    required = (
        "bundle_id", "display_name", "engine_version", "economics_version",
        "economics_digest", "packet_version", "seed", "candidate_pool_hash",
        "schema_version",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise BundleError(f"bundle is missing required keys: {missing}")
    if int(data["schema_version"]) != BUNDLE_SCHEMA_VERSION:
        raise BundleError(
            f"bundle schema {data['schema_version']} is not supported "
            f"(this service speaks {BUNDLE_SCHEMA_VERSION})"
        )
    return GameBundle(
        bundle_id=str(data["bundle_id"]),
        display_name=str(data["display_name"]),
        engine_version=str(data["engine_version"]),
        economics_version=str(data["economics_version"]),
        economics_digest=str(data["economics_digest"]),
        packet_version=str(data["packet_version"]),
        seed=int(data["seed"]),
        candidate_pool_hash=str(data["candidate_pool_hash"]),
        schema_version=int(data["schema_version"]),
        description=str(data.get("description", "")),
    )


@lru_cache(maxsize=None)
def list_bundles() -> Tuple[GameBundle, ...]:
    """Every bundle on disk, sorted by id."""
    if not BUNDLE_DIR.exists():
        return ()
    out: List[GameBundle] = []
    for path in sorted(BUNDLE_DIR.glob("*.json")):
        out.append(_bundle_from_dict(json.loads(path.read_text())))
    return tuple(out)


def load_bundle(bundle_id: str) -> GameBundle:
    """Resolve a bundle id. Unknown ids are an error, never a default."""
    for bundle in list_bundles():
        if bundle.bundle_id == bundle_id:
            return bundle
    known = [b.bundle_id for b in list_bundles()] or ["<none installed>"]
    raise BundleError(
        f"unknown bundle '{bundle_id}'. Installed bundles: {', '.join(known)}"
    )


def default_bundle() -> Optional[GameBundle]:
    """The bundle a session should use when none is named."""
    bundles = list_bundles()
    return bundles[0] if bundles else None


def verify_bundle_integrity(bundle: GameBundle) -> Tuple[bool, str]:
    """Does this bundle still describe the seed it claims to?

    Two independent checks: the live economics must still digest to the recorded
    value, and the seed must still produce the recorded candidate pool.
    """
    live_econ = economics_digest()
    if live_econ != bundle.economics_digest:
        return False, (
            "economic coefficients have changed since this bundle was frozen "
            f"(recorded {bundle.economics_digest[:12]}…, live {live_econ[:12]}…)"
        )
    live_pool = pool_hash_for_seed(bundle.seed)
    if live_pool != bundle.candidate_pool_hash:
        return False, (
            "the property pool for this bundle's seed has changed "
            f"(recorded {bundle.candidate_pool_hash[:12]}…, live {live_pool[:12]}…)"
        )
    return True, "bundle matches the live engine"


def game_config_for_bundle(bundle: GameBundle, **overrides) -> GameConfig:
    """A GameConfig pinned to this bundle's seed."""
    kwargs = dict(
        seed=bundle.seed,
        starting_equity=100.0,
        total_rounds=4,
        properties_per_round=4,
        practice_round=True,
        scenario="Base Case",
    )
    kwargs.update(overrides)
    return GameConfig(**kwargs)


def require_published_seed(seed: int) -> None:
    """Refuse any seed that is not the one the packet was published against.

    Sessions must be seed-pinned. A mismatched seed would invalidate every
    pre-built student model while leaving the property ids intact, so it fails
    here rather than in front of a class.
    """
    if seed != PUBLISHED_SEED:
        raise BundleError(
            f"seed {seed} is not the published dataset seed ({PUBLISHED_SEED}); "
            "create a session from a bundle instead of choosing a seed"
        )
