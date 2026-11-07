#!/usr/bin/env bash
# Put the demo VM back in its prepared state after people have used it.
#
#   scripts/reset_demo.sh "A. Reviewer"
#
# Empties the database and the bucket, reseeds the package and the action catalogue, runs each
# recipe, approves the fixes checked against the 2023-24 known issues in that person's name, and
# runs again. Run it from the repo root on the VM, with the app profile up.
set -euo pipefail
reviewer="${1:?the name to record on the approvals, for example \"A. Reviewer\"}"
cd "$(git rev-parse --show-toplevel)/infra"
docker compose exec -T api python -m navigator.demo reset --reviewer "$reviewer"
