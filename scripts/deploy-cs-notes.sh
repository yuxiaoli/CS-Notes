#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
repo=yuxiaoli/CS-Notes
branch=develop
local_sha="$(git rev-parse HEAD)"
remote_sha="$(gh api "repos/$repo/branches/$branch" --jq .commit.sha)"
test "$(git branch --show-current)" = "$branch" && test "$local_sha" = "$remote_sha" &&
  test -z "$(git status --porcelain --untracked-files=no)" ||
  { echo 'Publish a clean develop commit to the fork first; this command never pushes.' >&2; exit 1; }
gh workflow run cs-notes-pages.yml --repo "$repo" --ref "$branch"
