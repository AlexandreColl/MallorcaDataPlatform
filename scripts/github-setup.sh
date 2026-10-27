#!/usr/bin/env bash
# Repository settings as code: merge options and branch protection (rulesets) for main and develop.
# Idempotent: re-running updates the existing rulesets instead of creating duplicates.
#
# Requirements: GitHub CLI authenticated (`gh auth login`) and the repo already pushed.
# Usage:        ./scripts/github-setup.sh [owner/repo]   (default: the repo of the current checkout)
set -euo pipefail

REPO=${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}
echo "configuring $REPO"

# Merge strategy: squash features into develop, merge commits for release PRs into main.
gh repo edit "$REPO" \
  --default-branch develop \
  --enable-squash-merge \
  --enable-merge-commit \
  --enable-rebase-merge=false \
  --delete-branch-on-merge \
  --enable-auto-merge=false

# Status checks = job names in .github/workflows (they must have run at least once to be selectable in the UI).
CI_CHECKS='{"context": "Lint (ruff)"},
           {"context": "Unit tests (PySpark)"},
           {"context": "dbt build (empty warehouse)"},
           {"context": "Docker compose config + image build"},
           {"context": "conventional"}'

ruleset() {
  local name=$1 branch=$2 checks=$3
  cat <<JSON
{
  "name": "$name",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/$branch"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [$checks]
    }}
  ]
}
JSON
}

apply() {
  local name=$1 body=$2 id
  id=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$name\") | .id")
  if [[ -n "$id" ]]; then
    gh api -X PUT "repos/$REPO/rulesets/$id" --input - <<<"$body" >/dev/null && echo "updated ruleset '$name'"
  else
    gh api -X POST "repos/$REPO/rulesets" --input - <<<"$body" >/dev/null && echo "created ruleset '$name'"
  fi
}

# develop: PR + CI.  main: PR + CI + E2E with the real APIs.
apply "protect-develop" "$(ruleset protect-develop develop "$CI_CHECKS")"
apply "protect-main" "$(ruleset protect-main main "$CI_CHECKS, {\"context\": \"e2e\"}")"

# GitHub Pages served by the dbt-docs workflow (build_type workflow, no gh-pages branch).
if gh api "repos/$REPO/pages" >/dev/null 2>&1; then
  gh api -X PUT "repos/$REPO/pages" -f build_type=workflow >/dev/null && echo "pages: built by GitHub Actions"
else
  gh api -X POST "repos/$REPO/pages" -f build_type=workflow >/dev/null && echo "pages: enabled (GitHub Actions)"
fi

echo "done: https://github.com/$REPO/settings/rules"
