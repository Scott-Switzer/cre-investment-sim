"""
End-to-end smoke test of the engine service over real HTTP.

    uv run python scripts/verify_engine_service.py
    ENGINE_URL=http://localhost:8080 uv run python scripts/verify_engine_service.py

Starts the service as a **separate process** -- the way the container does -- waits
for it to answer, then plays a whole session through it: health, create, practice,
four scored rounds, a team view, and the final debrief.

Why this exists alongside `pytest`: the tests drive the ASGI app in-process, so they
cannot catch the things that only break when a process actually serves: a bad host or
port binding, an import that only resolves from the wrong working directory, a
missing file the app needs at runtime, or a dependency the tests happen to provide.
It is also the check to run against a container, by pointing `ENGINE_URL` at it.

Exit code is 0 only if every step passed. Nothing here is a substitute for the
contract fixtures; it is the "does it actually start and serve" gate.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}{(' -- ' + detail) if detail else ''}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def call(url: str, path: str, body: dict | None = None, method: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url + path,
        data=data,
        method=method or ("POST" if body is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _contains_number(payload, target: float, tolerance: float = 1e-9) -> bool:
    """Does any number anywhere in this payload equal `target`?

    Value-based rather than key-based, because a leaked reserve is usually a number
    under a new name, not a field called `reserve_price`.
    """
    if isinstance(payload, bool):
        return False
    if isinstance(payload, (int, float)):
        return abs(float(payload) - float(target)) < tolerance
    if isinstance(payload, dict):
        return any(_contains_number(value, target) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_number(item, target) for item in payload)
    return False


def wait_for_health(url: str, process: subprocess.Popen, seconds: int = 60) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            status, _ = call(url, "/v1/health")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    external = os.environ.get("ENGINE_URL")
    process: subprocess.Popen | None = None

    if external:
        url = external.rstrip("/")
        print(f"Smoke-testing a running service at {url}")
    else:
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        print(f"Starting the service on {url}")
        process = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "scripts" / "serve_engine.py")],
            cwd=str(REPO_ROOT),
            env={**os.environ, "PORT": str(port), "LOG_LEVEL": "warning"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    try:
        healthy = wait_for_health(url, process) if process else True
        if not healthy:
            print("  FAIL  the service never answered /v1/health")
            if process is not None and process.poll() is not None and process.stdout:
                print(process.stdout.read().decode()[-2000:])
            return 1

        print("\n1  health and datasets")
        status, health = call(url, "/v1/health")
        check("GET /v1/health is 200", status == 200, str(status))
        check("health reports the game", health.get("game") == "cre-investment-committee")
        check("health reports an economics digest",
              isinstance(health.get("economics_digest"), str)
              and len(health["economics_digest"]) == 64)

        status, listed = call(url, "/v1/bundles")
        bundles = listed.get("bundles") or []
        check("GET /v1/bundles lists a dataset", status == 200 and bool(bundles), str(status))
        check("the dataset listing carries no seed",
              all("seed" not in entry for entry in bundles))
        bundle_id = bundles[0]["bundle_id"]

        print("\n2  create a session")
        from service.engine_api import visibility
        from service.engine_api.fixtures import student_submissions

        status, created = call(url, "/v1/create-game-state", {
            "bundle_id": bundle_id,
            "teams": [
                {"team_id": "human", "team_name": "Student Fund",
                 "submissions": student_submissions()},
                {"team_id": "value", "team_name": "Value Fund"},
                {"team_id": "growth", "team_name": "Growth Fund"},
            ],
        })
        check("POST /v1/create-game-state is 200", status == 200, str(status)[:400])
        if status != 200:
            return 1
        state, public = created["state"], created["public"]
        check("the session opens in practice", public["stage"] == "PRACTICE")
        check("practice offers exactly one property", len(public["deals"]) == 1)

        status, _ = call(url, "/v1/create-game-state", {
            "bundle_id": bundle_id,
            "teams": [{
                "team_id": "wrong", "team_name": "Wrong",
                "submissions": [{
                    "property_id": "OC-NOT-REAL",
                    "forecast": {"predicted_fair_value": 1.0, "predicted_noi_growth": 0.0},
                    "policy": {"max_bid": 1.0, "target_ltv": 0.5},
                }],
            }],
        })
        check("a model for another dataset is refused", status == 409, str(status))

        print("\n3  practice, then four scored rounds")
        rounds_seen: list[int] = []
        for step in range(9):
            # Snapshot what a fund could see *before* deciding, so the reserves
            # revealed afterwards can be checked against it. A reserve that appears
            # in the payload the fund already received is the leak that ends the
            # exercise, and comparing the two is the only way to catch it from here.
            before_resolve = json.loads(json.dumps(public))

            decisions = []
            for deal in public["deals"]:
                # Every fund bids just above the asking price: enough to win
                # something, low enough that equity survives to the last round.
                for team_id in ("human", "value", "growth"):
                    decisions.append({
                        "team_id": team_id,
                        "property_id": deal["property_id"],
                        "action": "BID",
                        "bid": round(deal["asking_price"] * 1.01, 4),
                        "ltv": min(0.6, deal["max_ltv"]),
                    })
            status, resolved = call(url, "/v1/resolve-round",
                                    {"state": state, "decisions": decisions})
            if status != 200:
                check(f"resolve round {public['round_number']} is 200", False, str(status)[:300])
                return 1
            state = resolved["state"]
            round_number = resolved["public_results"]["round_number"]
            rounds_seen.append(round_number)

            revealed = [
                auction["reserve_price"]
                for auction in resolved["public_results"]["auctions"]
                if auction.get("reserve_price") is not None
            ]
            check(f"round {round_number} reveals its reserves", bool(revealed))
            check(
                f"round {round_number} hid every reserve it revealed",
                not any(_contains_number(before_resolve, value) for value in revealed),
            )
            check(
                f"round {round_number} keeps sealed bids sealed",
                "all_bids" not in json.dumps(resolved["public_results"]),
            )

            if resolved["game_complete"]:
                break
            status, opened = call(url, "/v1/open-round", {"state": state})
            if status != 200:
                check("open next round is 200", False, str(status)[:300])
                return 1
            state, public = opened["state"], opened["public"]
            check(
                f"round {public['round_number']} carries no reserve key",
                "reserve_price" not in json.dumps(public),
            )
            if opened["game_complete"]:
                break

        check("practice plus four scored rounds all resolved",
              sorted(rounds_seen) == [-1, 0, 1, 2, 3], str(rounds_seen))

        print("\n4  one fund's own view")
        status, view = call(url, "/v1/team-view", {"state": state, "team_id": "human"})
        check("POST /v1/team-view is 200", status == 200, str(status)[:200])
        check("the team view carries the fund's own model", bool(view.get("model_output")))
        # Checked by fund id rather than by searching the text: the substring
        # "value" occurs in every holding as `current_value`.
        named = visibility.collect_team_ids(view)
        check("the team view names no other fund", named <= {"human"}, str(sorted(named)))
        check("overrides were recorded", isinstance(view.get("overrides"), list))

        print("\n5  the debrief")
        status, final = call(url, "/v1/finalize-game", {"state": state})
        check("POST /v1/finalize-game is 200", status == 200, str(status)[:200])
        check("the game reports complete", final.get("game_complete") is True)
        check("ten questions are answered",
              len(final["debrief"]["answers"]) == 10
              and all(a["answer"] for a in final["debrief"]["answers"]))
        standings = final["standings"]
        check("every fund has a rank", len({row["rank"] for row in standings}) == len(standings))
        check("the standings are ordered by NAV",
              [row["nav"] for row in standings] == sorted(
                  (row["nav"] for row in standings), reverse=True))

        status, again = call(url, "/v1/finalize-game", {"state": state})
        check("finalising twice returns the same debrief",
              again["debrief"] == final["debrief"] and again["state"] == final["state"])

        if process is not None:
            print("\n6  a fresh process produces the same answer from the same state")
            # The property Cloud Run depends on: nothing lives in the instance. The
            # first server is stopped and a second one, which has never seen this
            # session, is given the same request.
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

            port = free_port()
            restarted = f"http://127.0.0.1:{port}"
            process = subprocess.Popen(
                [sys.executable, str(REPO_ROOT / "scripts" / "serve_engine.py")],
                cwd=str(REPO_ROOT),
                env={**os.environ, "PORT": str(port), "LOG_LEVEL": "warning"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if not wait_for_health(restarted, process):
                check("the restarted service answers /v1/health", False)
            else:
                status, replayed = call(restarted, "/v1/finalize-game", {"state": state})
                check("a restarted process serves the same session", status == 200, str(status))
                check("and returns the same standings",
                      replayed["standings"] == final["standings"])
                check("and the same debrief",
                      replayed["debrief"] == final["debrief"])

        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        if FAILED:
            print("failed checks: " + ", ".join(FAILED))
        return 1 if FAILED else 0
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
