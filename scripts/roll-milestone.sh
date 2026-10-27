#!/usr/bin/env bash
# Turn the "Next" milestone into the released version and open a fresh "Next".
#
#   scripts/roll-milestone.sh check X.Y.Z   fail if the roll would be ambiguous
#   scripts/roll-milestone.sh roll X.Y.Z    rename Next to X.Y.Z, carry its open
#                                           items over to a fresh Next, close X.Y.Z
#
# The release workflow runs "check" before tagging and "roll" after publishing.
# "roll" is safe to rerun after a partial or complete earlier roll: the rename
# stamps X.Y.Z's description with the marker below, and a milestone carrying it
# is resumed (open items moved, milestone closed) instead of rejected.
# Open issues and pull requests are moved rather than left behind, because a
# closed milestone with open items in it hides them from the next release.

set -euo pipefail

usage() { echo "usage: roll-milestone.sh check|roll X.Y.Z" >&2; exit 2; }
[[ $# -eq 2 ]] || usage
mode="$1"
version="$2"
[[ "$mode" == check || "$mode" == roll ]] || usage
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "::error::Version must match X.Y.Z (got: $version)" >&2; exit 2; }

REPO="${REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
export REPO
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

marker="Released in v$version."

milestone_field() {
    gh api --paginate "repos/$REPO/milestones?state=all&per_page=100" \
        --jq ".[] | select(.title == \"$1\") | .$2"
}

next="$(milestone_field Next number)"
released="$(milestone_field "$version" number)"
resumable=false
[[ -n "$released" && "$(milestone_field "$version" description)" == "$marker" ]] && resumable=true

# Before tagging, any X.Y.Z milestone next to Next is ambiguous; during the roll, one
# this script already renamed is not.
if [[ -n "$next" && -n "$released" ]] && { [[ "$mode" == check ]] || ! $resumable; }; then
    echo "::error::Both \"Next\" and \"$version\" milestones exist; merge them by hand before releasing" >&2
    exit 1
fi

if [[ "$mode" == check ]]; then
    echo "ok       milestones can roll to $version"
    exit 0
fi

if [[ -n "$next" && -z "$released" ]]; then
    gh api -X PATCH "repos/$REPO/milestones/$next" -f title="$version" \
        -f description="$marker" >/dev/null
    released="$next"
    echo "renamed  milestone Next -> $version"
fi

# Recreates the standing "Next" (and "Later" if missing) from the one list of truth.
"$script_dir/../.github/sync-labels.sh"

if [[ -z "$released" ]]; then
    echo "skipped  no Next milestone to close"
    exit 0
fi

fresh="$(milestone_field Next number)"
gh api --paginate "repos/$REPO/issues?milestone=$released&state=open&per_page=100" --jq '.[].number' |
    while IFS= read -r number; do
        gh api -X PATCH "repos/$REPO/issues/$number" -F milestone="$fresh" >/dev/null
        echo "moved    #$number -> Next"
    done

gh api -X PATCH "repos/$REPO/milestones/$released" -f state=closed >/dev/null
echo "closed   milestone $version"
