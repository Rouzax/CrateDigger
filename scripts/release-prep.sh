#!/usr/bin/env bash
# Print context useful for curating the [Unreleased] CHANGELOG section
# before cutting a stable release.
#
# Shows:
#   - commits since the most recent vX.Y.Z tag
#   - current contents of the [Unreleased] section
#   - the "Next" milestone: open items must be done or moved before a
#     release, closed ones are a cross-check for the CHANGELOG

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

last_tag=$(git describe --tags --abbrev=0 --match='v*.*.*' 2>/dev/null || echo "")

echo "=== Commits since ${last_tag:-<no previous release tag>} ==="
echo
if [[ -n "$last_tag" ]]; then
    git log "$last_tag..HEAD" --oneline
else
    git log --oneline
fi

echo
echo "=== Current [Unreleased] section in CHANGELOG.md ==="
echo
awk '
    /^## \[Unreleased\]/ { found=1; next }
    found && /^## \[/ { exit }
    found { print }
' CHANGELOG.md

echo
echo "=== Milestone \"Next\": open (finish or move before releasing) ==="
echo
gh issue list --milestone Next --state open --limit 200 \
    --json number,title --jq '.[] | "#\(.number) \(.title)"'

echo
echo "=== Milestone \"Next\": closed (each user-visible one belongs in the CHANGELOG) ==="
echo
gh issue list --milestone Next --state closed --limit 200 \
    --json number,title --jq '.[] | "#\(.number) \(.title)"'
gh pr list --search 'milestone:Next' --state merged --limit 200 \
    --json number,title --jq '.[] | "PR #\(.number) \(.title)"'
