#!/usr/bin/env bash
# Cut a release: verify prerequisites, then push a 'chore: release X.Y.Z' commit
# that triggers the GitHub Actions release workflow.
#
# Usage: scripts/release.sh [version]
#   If version is omitted, reads it from pyproject.toml.

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

# Determine version
if [[ $# -ge 1 ]]; then
    version="$1"
else
    version=$(grep -E '^version = "[0-9]+\.[0-9]+\.[0-9]+"' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
fi

if [[ -z "$version" ]]; then
    echo "error: could not determine version from pyproject.toml" >&2
    exit 1
fi

echo "Releasing version: $version"

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "error: uncommitted changes present; commit or stash them first" >&2
    exit 1
fi

# Verify pyproject.toml matches
got=$(grep -E '^version = "[0-9]+\.[0-9]+\.[0-9]+"' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
if [[ "$version" != "$got" ]]; then
    echo "error: requested version $version but pyproject.toml says $got" >&2
    exit 1
fi

# Verify CHANGELOG has a non-empty section for this version
if ! grep -qE "^## \[$version\]" CHANGELOG.md; then
    echo "error: CHANGELOG.md has no ## [$version] section" >&2
    echo "Run: scripts/release-prep.sh to see what belongs there" >&2
    exit 1
fi

section=$(awk -v ver="$version" '
    $0 ~ "^## \\["ver"\\]" { found=1; next }
    found && /^## \[/ { exit }
    found { print }
' CHANGELOG.md)

if [[ -z "${section// }" ]]; then
    echo "error: CHANGELOG.md ## [$version] section is empty" >&2
    exit 1
fi

# Verify tag does not already exist
tag="v$version"
if git rev-parse "$tag" &>/dev/null; then
    echo "error: tag $tag already exists locally" >&2
    exit 1
fi
if git ls-remote --exit-code origin "refs/tags/$tag" &>/dev/null; then
    echo "error: tag $tag already exists on origin" >&2
    exit 1
fi

echo
echo "CHANGELOG preview:"
echo "$section" | head -10
echo

read -r -p "Create and push 'chore: release $version' commit? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

git commit --allow-empty -m "chore: release $version"
git push origin HEAD

echo
echo "Done. GitHub Actions will pick up the release workflow."
