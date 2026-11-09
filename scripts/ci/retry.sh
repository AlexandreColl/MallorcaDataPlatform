#!/usr/bin/env bash
# Runs a command up to RETRY_ATTEMPTS times (default 4), waiting 15 s, 30 s, 45 s... between attempts.
# For the CI steps that download from GitHub releases, PyPI or Maven Central: a 502/504 of a few minutes
# should not fail the run.
#   scripts/ci/retry.sh pip install -r requirements/dbt.txt
set -uo pipefail

attempts="${RETRY_ATTEMPTS:-4}"
for ((i = 1; i <= attempts; i++)); do
  "$@" && exit 0
  status=$?
  if ((i == attempts)); then
    echo "::error::failed after ${attempts} attempts (exit ${status}): $*" >&2
    exit "$status"
  fi
  echo "::warning::attempt ${i}/${attempts} failed (exit ${status}), retrying in $((15 * i)) s: $*" >&2
  sleep $((15 * i))
done
