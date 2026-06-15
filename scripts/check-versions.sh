#!/usr/bin/env bash
# Verify the project version is consistent across every place it is recorded.
#
# Checks:
#   - pyproject.toml           version = "X.Y.Z"
#   - README.md                version badge (shields.io URL and alt text)
#   - CHANGELOG.md             ## [X.Y.Z] section exists and is non-empty
#
# Usage:
#   scripts/check-versions.sh            # check that README + CHANGELOG agree with pyproject.toml
#   scripts/check-versions.sh X.Y.Z      # also require every place to equal X.Y.Z
#
# Exits non-zero and prints every mismatch found (does not stop at the first).
# Run before cutting a release; the release workflow runs it too.

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

fail=0
err() { echo "error: $*" >&2; fail=1; }

# --- pyproject.toml ---------------------------------------------------------
pyproject_version=$(grep -E '^version = "[0-9]+\.[0-9]+\.[0-9]+"' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
if [[ -z "$pyproject_version" ]]; then
    err "could not find a version in pyproject.toml"
fi

# The expected version: the argument if given, otherwise pyproject.toml.
want="${1:-$pyproject_version}"
if [[ ! "$want" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    err "version must match X.Y.Z (got: $want)"
    echo "FAIL" >&2
    exit 1
fi

if [[ -n "$pyproject_version" && "$pyproject_version" != "$want" ]]; then
    err "pyproject.toml version ($pyproject_version) does not match expected ($want)"
fi

# --- README.md badge --------------------------------------------------------
readme_badge=$(grep -oE 'badge/version-v[0-9]+\.[0-9]+\.[0-9]+-' README.md | head -1 | sed -E 's#badge/version-v(.+)-#\1#')
if [[ -z "$readme_badge" ]]; then
    err "could not find a version badge in README.md"
elif [[ "$readme_badge" != "$want" ]]; then
    err "README.md badge version ($readme_badge) does not match expected ($want)"
fi

readme_alt=$(grep -oE 'alt="v[0-9]+\.[0-9]+\.[0-9]+"' README.md | head -1 | sed -E 's/alt="v(.+)"/\1/')
if [[ -n "$readme_alt" && "$readme_alt" != "$want" ]]; then
    err "README.md badge alt text ($readme_alt) does not match expected ($want)"
fi

# --- CHANGELOG.md section ---------------------------------------------------
if ! grep -qE "^## \[$want\]" CHANGELOG.md; then
    err "CHANGELOG.md has no ## [$want] section"
else
    section=$(awk -v ver="$want" '
        $0 ~ "^## \\["ver"\\]" { found=1; next }
        found && /^## \[/ { exit }
        found { print }
    ' CHANGELOG.md)
    if [[ -z "$(echo "$section" | tr -d '[:space:]')" ]]; then
        err "CHANGELOG.md [$want] section is empty"
    fi
fi

if [[ "$fail" -ne 0 ]]; then
    echo "FAIL: version is not consistent for $want" >&2
    exit 1
fi

echo "OK: version $want is consistent across pyproject.toml, README.md, and CHANGELOG.md"
