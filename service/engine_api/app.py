"""
The engine service HTTP surface.

Six routes, and one property that matters more than any of them: **every route is a
pure function of its request body**. The caller passes the whole game state in and
gets the whole next state back. Nothing is cached, nothing is keyed by a session id,
and no instance holds a game in memory -- so a Cloud Run instance can be recycled,
scaled to zero, or replaced mid-round without the game noticing.

That is also why there is no authentication *inside* this service and no session
table: it is a calculator. It is expected to be reachable only from the game service
over IAM/OIDC, and to have no public route at all.

The response to ``resolve-round`` is **trusted server state** and is not what a
browser may see. Projection into player-safe payloads lives in ``public.py`` and the
game service is the only party that calls it.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import bundles, engine, public, serde
from .bundles import BundleError, BundleIntegrityError
from .contracts import (
    BundleSummary,
    CreateGameStateRequest,
    CreateGameStateResponse,
    FinalizeGameRequest,
    FinalizeGameResponse,
    HealthResponse,
    ListBundlesResponse,
    OpenRoundRequest,
    OpenRoundResponse,
    ResolveRoundRequest,
    ResolveRoundResponse,
)
from .engine import EngineOpError
from .serde import SerdeError
from .visibility import LeakError

# An integrity failure here means the service built a payload it should not have.
# It is not a client error and must never be retried away, so it is a 500 with a
# distinct body rather than a 4xx the caller could mistake for bad input.
LEAK_STATUS = 500


def create_app() -> FastAPI:
    app = FastAPI(
        title="CRE Investment Committee — Engine Service",
        version="0.1.0",
        description=(
            "Private, stateless adjudication for the REAL 605 CRE simulation. "
            "Server-to-server only; the browser must never reach this service."
        ),
    )

    # ── error translation ────────────────────────────────────────────────
    #
    # The engine expresses failures in its own vocabulary; HTTP has its own. The
    # mapping is explicit so a caller can tell "your input was wrong" (400) from
    # "your state does not allow that" (409) without parsing prose.

    @app.exception_handler(BundleIntegrityError)
    async def _bundle_integrity_error(_request, exc: BundleIntegrityError) -> JSONResponse:
        # A dataset whose economics drifted is a deployment fault, not bad input.
        # 500 rather than 400 so a caller does not treat it as something to correct.
        return JSONResponse(
            status_code=500,
            content={"error": "bundle_integrity", "detail": str(exc)},
        )

    @app.exception_handler(BundleError)
    async def _bundle_error(_request, exc: BundleError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "bundle", "detail": str(exc)})

    @app.exception_handler(SerdeError)
    async def _serde_error(_request, exc: SerdeError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "state", "detail": str(exc)})

    @app.exception_handler(EngineOpError)
    async def _op_error(_request, exc: EngineOpError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "illegal_operation", "detail": str(exc)})

    @app.exception_handler(LeakError)
    async def _leak_error(_request, exc: LeakError) -> JSONResponse:
        return JSONResponse(status_code=LEAK_STATUS, content={"error": "integrity", "detail": str(exc)})

    # ── health ───────────────────────────────────────────────────────────

    @app.get("/v1/health", response_model=HealthResponse)
    def health() -> Dict[str, Any]:
        return engine.health()

    # ── datasets ─────────────────────────────────────────────────────────

    @app.get("/v1/bundles", response_model=ListBundlesResponse)
    def list_bundles() -> Dict[str, Any]:
        """The datasets a professor may select. Note the absence of a seed."""
        return {
            "bundles": [
                BundleSummary(
                    bundle_id=b.bundle_id,
                    display_name=b.display_name,
                    packet_version=b.packet_version,
                    economics_version=b.economics_version,
                    description=b.description,
                )
                for b in bundles.list_bundles()
            ]
        }

    @app.get("/v1/bundles/{bundle_id}")
    def get_bundle(bundle_id: str) -> Dict[str, Any]:
        """Bundle metadata *including* the integrity check, for an operator.

        Exposes the seed and the hashes deliberately: this route is for diagnosing
        a dataset, not for players. It stays server-side with the rest.
        """
        bundle = bundles.load_bundle(bundle_id)
        ok, message = bundles.verify_bundle_integrity(bundle)
        payload = bundle.to_dict()
        payload["integrity_ok"] = ok
        payload["integrity_message"] = message
        return payload

    @app.get("/v1/bundles/{bundle_id}/pool")
    def get_bundle_pool(bundle_id: str) -> Dict[str, Any]:
        """The bundle's candidate pool, projected for players.

        The game service needs this to validate an uploaded model before it commits
        a session to a dataset, and to build the model check-in report. It is the
        same property DTO the round loop serves, so the game has exactly one
        representation of a building. See ``engine.bundle_pool``.
        """
        return engine.bundle_pool(bundle_id)

    # ── the round loop ───────────────────────────────────────────────────

    @app.post("/v1/create-game-state", response_model=CreateGameStateResponse)
    def create_game_state(request: CreateGameStateRequest) -> Dict[str, Any]:
        bundle, state, public_round = engine.create_game_state(
            request.bundle_id,
            request.teams,
            request.scenario,
            request.course_mode,
            request.management_enabled,
        )
        return {
            "bundle": bundle.to_dict(),
            "state": state,
            "public": public_round,
        }

    @app.post("/v1/open-round", response_model=OpenRoundResponse)
    def open_round(request: OpenRoundRequest) -> Dict[str, Any]:
        state, public_round, complete = engine.open_round(request.state)
        return {"state": state, "public": public_round, "game_complete": complete}

    @app.post("/v1/resolve-round", response_model=ResolveRoundResponse)
    def resolve_round(request: ResolveRoundRequest) -> Dict[str, Any]:
        state, results, analytics, rejected, rejected_stances, complete = engine.resolve_round(
            request.state, request.decisions, request.management_stances
        )
        return {
            "state": state,
            "public_results": results,
            "analytics_updates": analytics,
            "rejected_decisions": rejected,
            "rejected_stances": rejected_stances,
            "game_complete": complete,
        }

    @app.post("/v1/finalize-game", response_model=FinalizeGameResponse)
    def finalize_game(request: FinalizeGameRequest) -> Dict[str, Any]:
        state, standings, analytics, debrief = engine.finalize_game(request.state)
        gm_complete = bool(state.get("game_complete"))
        return {
            "state": state,
            "standings": standings,
            "analytics": analytics,
            "debrief": debrief,
            "game_complete": gm_complete,
        }

    # ── the one team-scoped route ────────────────────────────────────────

    @app.post("/v1/team-view")
    def team_view(body: Dict[str, Any]) -> Dict[str, Any]:
        """One fund's own forecast, policy, book and overrides — and nobody else's.

        The game service serves this to the owning fund only. The payload asserts
        that it names no other fund, because this is the response where a leak
        would be a rival team's model.
        """
        state = body.get("state")
        team_id = body.get("team_id")
        if not isinstance(state, dict) or not isinstance(team_id, str):
            raise HTTPException(422, "expected {state: object, team_id: string}")
        gm = serde.restore_game(state)
        try:
            return public.team_private_view(gm, team_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    return app


app = create_app()
