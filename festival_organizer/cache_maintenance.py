"""Structural artwork-cache hygiene.

Logging:
    Logger: 'festival_organizer.cache_maintenance'
    Key events:
        - cache.reconcile.removed (DEBUG): an orphaned artist dir was deleted
        - cache.reconcile.summary (INFO): count of dirs removed this run
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def reconcile_artist_cache(artists_root: Path, valid_folder_slugs: set[str]) -> list[Path]:
    """Delete cache/artists/* dirs whose name is not a valid folder-ified slug.

    The canonical set is the folder_slug() of every known dj_cache slug. Old
    display-name dirs, mojibake variants and truncations are removed; enrich
    re-populates the canonical slug dirs on the same run. Idempotent.

    Returns the list of removed directories.
    """
    if not artists_root.exists():
        return []
    removed: list[Path] = []
    for child in artists_root.iterdir():
        if not child.is_dir():
            continue
        if child.name in valid_folder_slugs:
            continue
        try:
            shutil.rmtree(child)
            removed.append(child)
            logger.debug("cache.reconcile.removed: dir=%s", child.name)
        except OSError as exc:
            logger.debug("cache.reconcile.failed: dir=%s error=\"%s\"", child.name, exc)
    if removed:
        logger.info("cache.reconcile.summary: removed=%d", len(removed))
    return removed
