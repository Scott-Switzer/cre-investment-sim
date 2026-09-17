#!/bin/bash
cd "$(dirname "$0")/../.." || exit 1
exec firebase emulators:exec --only firestore --project demo-cre -- 'sleep 1800'
