# CrateDigger

Festival set & concert library manager. Organizes, enriches, and tags media files with artwork, metadata, and chapter markers.

## Logging conventions

- All output routes through a shared Rich Console on stdout (progress, logging, spinners)
- Rich auto-strips formatting when stdout is piped
- WARNING: failures that don't stop the pipeline
- INFO (`--verbose`): key decisions, external actions, parse results
- DEBUG (`--debug`): cache, retries, internal mechanics
- See `.claude/docs/logging.md` for the full contract

## Writing style

- Never use em-dashes (--) in code, comments, commit messages, or any output. Use commas, semicolons, or separate sentences instead.

## Git conventions

- Do not add `Co-Authored-By` trailers to commits.
