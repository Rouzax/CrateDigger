#!/usr/bin/env bash
# Print context useful for curating the [Unreleased] CHANGELOG section
# before cutting a stable release.
#
# Shows:
#   - commits since the most recent vX.Y.Z tag
#   - current contents of the [Unreleased] section

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
