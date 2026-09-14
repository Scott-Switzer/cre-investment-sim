#!/bin/bash
# Start the Firestore emulator and hold it open while the Playwright suite runs.
#
# `firebase emulators:exec` demands a script argument and re-parses that argument
# through a shell, so it must arrive *quoted*. Playwright spawns its webServer
# command as an argv array — no shell — which is why this file exists: it is the
# shell. The waiter holds for 30 minutes, far longer than any run, and dies with
# this process when Playwright tears the webServer down.
#
# cd first: firebase.json (which pins the emulator to :8085) lives in services/game,
# and the CLI without it happily starts Firestore on its default port 8080 — the
# port the game service itself listens on.
cd "$(dirname "$0")/../.." || exit 1
exec firebase emulators:exec --only firestore --project demo-cre -- 'sleep 1800'
