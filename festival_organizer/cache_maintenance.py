"""Structural artwork-cache hygiene.

Logging:
    Logger: 'festival_organizer.cache_maintenance'
    Key events:
        - cache.reconcile.removed (DEBUG): an orphaned artist dir was deleted
        - cache.reconcile.summary (INFO): count of dirs removed this run
        - cache.warm.summary (INFO): count of artist dirs newly populated this run
        - enrich.dj_artwork_download (INFO): a DJ artwork image was downloaded
        - enrich.dj_artwork (DEBUG): crop/resize applied to a downloaded image
        - enrich.dj_artwork_cache (DEBUG): a stale cached image was replaced
"""

import logging
import shutil
import time
from pathlib import Path

from festival_organizer.cache_ttl import hashed_jitter_factor
from festival_organizer.normalization import folder_slug

logger = logging.getLogger(__name__)


def cache_dj_artwork(
    url: str,
    dest: Path,
    ttl_days: float,
    *,
    artist_label: str = "",
    log: logging.Logger | None = None,
) -> Path | None:
    """Download DJ artwork to ``dest``, center-crop to square, resize to 550, save JPEG.

    ``dest`` is ``.../artists/<slug>/dj-artwork.jpg``. Honours a jittered TTL: a
    fresh cached file is reused as-is (returned without re-downloading); a stale
    one is replaced. Returns ``dest`` on success (cached or freshly written),
    or ``None`` on download/decode failure.

    ``log`` lets callers route the ``enrich.dj_artwork*`` events through their own
    logger so existing per-file logging output is preserved; defaults to this
    module's logger.
    """
    import io

    out = log or logger
    if not url:
        return None
    if dest.exists():
        age_days = (time.time() - dest.stat().st_mtime) / 86400
        effective_ttl = ttl_days * hashed_jitter_factor(dest.name)
        if age_days <= effective_ttl:
            return dest
        dest.unlink()
        out.debug(
            "enrich.dj_artwork_cache: status=stale age_days=%d ttl=%.1f artist=%s",
            int(age_days),
            effective_ttl,
            artist_label,
        )
    try:
        import requests
        from PIL import Image

        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(resp.content)) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w != h:
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                out.debug(
                    "enrich.dj_artwork: action=crop from=%dx%d to=%dx%d",
                    w,
                    h,
                    side,
                    side,
                )
            max_side = 550
            if img.width > max_side:
                img = img.resize((max_side, max_side), Image.Resampling.LANCZOS)
                out.debug(
                    "enrich.dj_artwork: action=resize to=%dx%d", max_side, max_side
                )
            img.save(dest, "JPEG", quality=90)
        out.info(
            "enrich.dj_artwork_download: status=ok artist=%s target=%s",
            artist_label,
            dest,
        )
        return dest
    except Exception as e:
        out.debug(
            'enrich.dj_artwork_download: status=failed artist=%s error="%s"',
            artist_label,
            e,
        )
        return None


def warm_artist_cache_from_dj_cache(
    artists_root: Path, dj_cache, ttl_days: float
) -> list[Path]:
    """Ensure ``artists/<folder_slug(slug)>/dj-artwork.jpg`` exists for every cached DJ.

    Iterates :meth:`DjCache.all_artwork_urls` and downloads artwork for any cached
    DJ that has an ``artwork_url`` but a missing/stale image. This is the CREATE
    counterpart to :func:`reconcile_artist_cache`: it keys directories by
    ``folder_slug(slug)`` exactly like the reconcile valid set, so warmed dirs are
    never reaped. Downloads are TTL-gated, so repeat runs are cheap. Idempotent.

    Returns the list of artist directories that were newly populated this run.
    """
    created: list[Path] = []
    for slug, url in dj_cache.all_artwork_urls().items():
        dest = artists_root / folder_slug(slug) / "dj-artwork.jpg"
        existed = dest.exists()
        result = cache_dj_artwork(url, dest, ttl_days, artist_label=slug)
        if result is not None and not existed:
            created.append(dest.parent)
    if created:
        logger.info("cache.warm.summary: created=%d", len(created))
    return created


def reconcile_artist_cache(
    artists_root: Path, valid_folder_slugs: set[str]
) -> list[Path]:
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
            logger.debug('cache.reconcile.failed: dir=%s error="%s"', child.name, exc)
    if removed:
        logger.info("cache.reconcile.summary: removed=%d", len(removed))
    return removed
