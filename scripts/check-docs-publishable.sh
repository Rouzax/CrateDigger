#!/usr/bin/env bash
# Fail if docs/ contains anything git ignores.
#
# docs/ is the Zensical source tree, and Zensical builds and full-text indexes
# every file it finds there. It has no exclude_docs, not_in_nav or draft_docs
# equivalent; docs_dir and site_dir are the only file-selection settings it
# reads. So a working document parked under docs/ cannot be held out of the
# build by configuration: it renders as an orphan page and its contents land in
# search.json, reachable from the site's own search box.
#
# CI builds from a clean checkout, so ignored files never exist there and this
# check can only ever be meaningful locally. That is why it is a commit hook
# rather than a workflow step.
#
# Working documents (plans, specs, internal contracts) belong in .claude/.
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

# --others --ignored lists ignored files that are not tracked. --directory
# collapses a wholly ignored directory to one entry instead of listing every
# file beneath it.
offenders=$(git ls-files --others --ignored --exclude-standard --directory -- docs/)

if [[ -n "$offenders" ]]; then
    echo "docs/ contains git-ignored paths:" >&2
    echo >&2
    printf '  %s\n' $offenders >&2
    echo >&2
    echo "Everything under docs/ is built and indexed into the published site." >&2
    echo "Move working documents to .claude/plans/ or .claude/specs/ instead." >&2
    exit 1
fi
