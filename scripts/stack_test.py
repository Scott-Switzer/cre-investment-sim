#!/usr/bin/env python3
"""
Start the complete local stack for Phase 2 browser testing:

    uv run python scripts/stack_test.py            # engine 8081, game service 8080
    STACK_ENGINE_PORT=8091 ...                     # custom ports

Components
----------
1. the Python engine (uvicorn, stateless adjudicator) on :8081
2. the Node game service, Firestore-backed against the emulator on :8085,
   serving the built React client and the API on :8080

The Firestore emulator itself is started by the Playwright webServer hook (or by
`firebase emulators:exec`), so this script only needs the emulator to be reachable
before the game service boots. Wait-for-health is built in; everything is torn down
on SIGTERM/SIGINT so `emulators:exec` can shut the whole tree down cleanly.

Env the game service is given:
    STORE=firestore          FirestoreStore, emulator-backed
    FIRESTORE_EMULATOR_HOST  the emulator's host:port
    COOKIE_SECRET            a fixed development secret (>= 32 chars)
    COOKIE_INSECURE=1        cookies over plain HTTP, local only
    ENGINE_URL               the engine started above
    CLIENT_DIST              the built client (dist/client)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GAME = REPO / "services" / "game"

ENGINE_PORT = int(os.environ.get("STACK_ENGINE_PORT", "8081"))
GAME_PORT = int(os.environ.get("STACK_GAME_PORT", "8080"))
EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8085")
COOKIE_SECRET = os.environ.get("STACK_COOKIE_SECRET", "phase2-local-dev-secret-0123456789abcdef")


def wait_for(url: str, deadline_s: float = 90.0) -> None:
    started = time.time()
    last = "no attempt"
    while time.time() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=3) as res:
                if res.status < 500:
                    return
        except urllib.error.URLError as exc:
            last = str(exc)
        except Exception as exc:  # noqa: BLE001 - reporting only
            last = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"{url} never became healthy ({last})")


def wait_for_firestore_game(url: str, deadline_s: float = 90.0) -> None:
    """Require the exact store identity expected by the classroom browser run."""
    started = time.time()
    last = "no attempt"
    while time.time() - started < deadline_s:
        try:
            with urllib.request.urlopen(url, timeout=3) as res:
                import json
                body = json.load(res)
                if body.get("status") == "ok" and body.get("store") == "firestore":
                    return
                last = f"unexpected health identity: {body}"
        except urllib.error.URLError as exc:
            last = str(exc)
        except Exception as exc:  # noqa: BLE001 - reporting only
            last = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"{url} did not report Firestore identity ({last})")


def _load_project_id():
    try:
        with open("/tmp/fenrix-firestore-project-id") as f:
            return f.read().strip()
    except Exception:
        return "demo-cre"


def main() -> int:
    engine_port = ENGINE_PORT
    game_port = GAME_PORT

    # A fresh, minimal environment: inheriting the caller's stdio fds made Popen
    # raise Errno 9 (Bad file descriptor) under `emulators:exec`, which runs its
    # children with unusual descriptor state.
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(Path.home())),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }

    engine = subprocess.Popen(
        [str(REPO / ".venv" / "bin" / "python"), "scripts/serve_engine.py"],
        cwd=REPO,
        env={**env, "PORT": str(engine_port), "HOST": "127.0.0.1", "LOG_LEVEL": "warning"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    game = subprocess.Popen(
        ["node", "dist/index.js"],
        cwd=GAME,
        env={
            **env,
            "PORT": str(game_port),
            "HOST": "127.0.0.1",
            "STORE": "firestore",
            "FIRESTORE_EMULATOR_HOST": EMULATOR_HOST,
            "GOOGLE_CLOUD_PROJECT": "demo-cre",
            "COOKIE_SECRET": COOKIE_SECRET,
            "COOKIE_INSECURE": "1",
            "ENGINE_URL": f"http://127.0.0.1:{engine_port}",
            "CLIENT_DIST": str(GAME / "dist" / "client"),
            "PROFESSOR_PASSCODE": os.environ.get("PROFESSOR_PASSCODE", "frenzel"),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    def shutdown(_signum: int, _frame: object) -> None:
        # The children sit in their own sessions, so SIGTERM the process groups.
        for proc in (game, engine):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Wait for Firestore emulator to accept TCP connections before starting game service
    def wait_for_emulator(host_port: str, deadline_s: float = 30.0) -> None:
        """Wait for the emulator to accept TCP connections."""
        import socket
        host, port = host_port.split(":")
        started = time.time()
        while time.time() - started < deadline_s:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    s.connect((host, int(port)))
                    return
            except (ConnectionRefusedError, OSError):
                pass
            time.sleep(0.3)
        raise RuntimeError(f"Emulator at {host_port} never became reachable")

    try:
        wait_for_emulator(EMULATOR_HOST)
        wait_for(f"http://127.0.0.1:{engine_port}/v1/health")
        print(f"engine healthy on :{engine_port}", flush=True)
        wait_for_firestore_game(f"http://127.0.0.1:{game_port}/v1/health")
        print(f"game service healthy on :{game_port} (client at /)", flush=True)
        # Stay in the foreground for the lifetime of the stack.
        while True:
            if engine.poll() is not None or game.poll() is not None:
                print("a stack component exited; shutting down", file=sys.stderr, flush=True)
                return 1
            time.sleep(1)
    except Exception as exc:  # noqa: BLE001
        print(f"stack failed to start: {exc}", file=sys.stderr, flush=True)
        shutdown(0, None)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
