"""Vulture allowlist: names that are used dynamically, required by a protocol,
or kept as deliberate public-API surface, and would otherwise be reported as
dead code. Each entry must carry a comment explaining why it is actually used.

This file is passed to vulture alongside the package so the references below
count as uses:

    vulture festival_organizer vulture_allowlist.py --min-confidence 80

Vulture matches by name, so each allowlisted name is simply referenced below.
"""


def _allowlist_unused_names() -> None:
    """Reference names vulture would otherwise flag. Never called."""
    # Context-manager protocol: StepProgress.__exit__ must accept the three
    # exception arguments even though it ignores them (it just calls stop()).
    # The names are mandated by the with-statement protocol, not dead.
    exc_type = exc_val = exc_tb = None  # StepProgress.__exit__ signature

    # TracklistClient.search(query, duration_minutes=..., year=...): the
    # duration_minutes parameter is part of the public method signature and is
    # passed explicitly by the identify CLI handler (tracklists/cli_handler.py).
    # The 1001TL search POST does not filter by duration; duration matching
    # happens later in score_results(). Kept as documented API surface.
    duration_minutes = 0

    # format_freshness_line(..., package_name): kept in the signature for
    # cross-repo symmetry with the TrackSplit twin module (documented in the
    # function's docstring). The body uses the module-level PACKAGE_NAME via
    # _upgrade_command(); the parameter is intentional public-API surface.
    package_name = ""

    _ = (exc_type, exc_val, exc_tb, duration_minutes, package_name)
