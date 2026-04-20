#!/usr/bin/env bash
# Install the project's Git hooks for this clone.
# Run once after cloning:  ./scripts/setup-hooks.sh

set -euo pipefail

git config core.hooksPath scripts/git-hooks
echo "Configured core.hooksPath = scripts/git-hooks"
echo "Installed hooks:"
ls -1 scripts/git-hooks/
