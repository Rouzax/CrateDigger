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
        - enrich.deezer_download, enrich.deezer, enrich.deezer_cache: the same
          three for a Deezer artist photo
        - cache.portrait (DEBUG): an artist's portrait.jpg was written or removed
"""

import logging
import shutil
import time
from pathlib import Path

from festival_organizer.cache_ttl import hashed_jitter_factor
from festival_organizer.deezer import resolve_deezer_photo
from festival_organizer.fanart import lookup_mbid
from festival_organizer.normalization import folder_slug

logger = logging.getLogger(__name__)


# Each artist image source's file in an artist's cache directory, keyed by its
# token in artist_background_priority.
ARTIST_IMAGE_FILES = {
    "deezer": "deezer-artist.jpg",
    "dj_artwork": "dj-artwork.jpg",
    "fanart_tv": "fanart.jpg",
}


def preferred_artist_image(artist_dir: Path, priority: list[str]) -> Path | None:
    """The first cached image in ``priority`` order, or None.

    Tokens without a cached file (``gradient``, place sources) are skipped.
    """
    for source in priority:
        name = ARTIST_IMAGE_FILES.get(source)
        if name and (artist_dir / name).exists():
            return artist_dir / name
    return None


def _is_fresh_image(dest: Path, ttl_days: float) -> bool:
    if not dest.exists():
        return False
    age_days = (time.time() - dest.stat().st_mtime) / 86400
    return age_days <= ttl_days * hashed_jitter_factor(dest.name)


def _cache_square_image(
    url: str,
    dest: Path,
    ttl_days: float,
    *,
    event: str,
    artist_label: str,
    log: logging.Logger,
) -> Path | None:
    """Download an artist image to ``dest``: center-crop to square, cap at 550, JPEG.

    Both artist covers (CrateDigger's poster tile and TrackSplit's photo) are
    drawn 550 px square, so a larger source gains nothing. Honours a jittered
    TTL: a fresh cached file is reused as-is; a stale one is replaced. Returns
    ``dest`` on success (cached or freshly written), or None on
    download/decode failure. Log events are ``enrich.<event>_download``,
    ``enrich.<event>`` and ``enrich.<event>_cache``.
    """
    import io

    if not url:
        return None
    if dest.exists():
        if _is_fresh_image(dest, ttl_days):
            return dest
        age_days = (time.time() - dest.stat().st_mtime) / 86400
        dest.unlink()
        log.debug(
            "enrich.%s_cache: status=stale age_days=%d ttl=%.1f artist=%s",
            event,
            int(age_days),
            ttl_days * hashed_jitter_factor(dest.name),
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
                log.debug(
                    "enrich.%s: action=crop from=%dx%d to=%dx%d",
                    event,
                    w,
                    h,
                    side,
                    side,
                )
            max_side = 550
            if img.width > max_side:
                img = img.resize((max_side, max_side), Image.Resampling.LANCZOS)
                log.debug(
                    "enrich.%s: action=resize to=%dx%d", event, max_side, max_side
                )
            img.save(dest, "JPEG", quality=90)
        log.info(
            "enrich.%s_download: status=ok artist=%s target=%s",
            event,
            artist_label,
            dest,
        )
        return dest
    except Exception as e:
        log.debug(
            'enrich.%s_download: status=failed artist=%s error="%s"',
            event,
            artist_label,
            e,
        )
        return None


def cache_dj_artwork(
    url: str,
    dest: Path,
    ttl_days: float,
    *,
    artist_label: str = "",
    log: logging.Logger | None = None,
) -> Path | None:
    """Download DJ artwork to ``dest`` (``.../artists/<slug>/dj-artwork.jpg``).

    See :func:`_cache_square_image`. ``log`` lets callers route the
    ``enrich.dj_artwork*`` events through their own logger so existing
    per-file logging output is preserved; defaults to this module's logger.
    """
    return _cache_square_image(
        url,
        dest,
        ttl_days,
        event="dj_artwork",
        artist_label=artist_label,
        log=log or logger,
    )


def cache_deezer_artwork(
    url: str, dest: Path, ttl_days: float, *, artist_label: str = ""
) -> Path | None:
    """Download a Deezer artist photo to ``dest`` (``.../deezer-artist.jpg``)."""
    return _cache_square_image(
        url, dest, ttl_days, event="deezer", artist_label=artist_label, log=logger
    )


def fetch_deezer_artwork(
    artist_name: str,
    dest: Path,
    *,
    spotify_url: str,
    mbid_cache,
    mbid_overrides,
    deezer_cache,
    deezer_overrides,
    ttl_days: float,
) -> Path | None:
    """The artist's Deezer photo cached at ``dest``, resolving it when needed.

    A fresh cached photo is used without any request. Otherwise the artist's
    MBID (through their Spotify page when known) leads to their Deezer photo.
    None when the artist has no Deezer photo or it could not be had; a
    previously cached photo is then left for its TTL rather than removed,
    since "no photo" and "Deezer did not answer" look the same here.
    """
    if _is_fresh_image(dest, ttl_days):
        return dest
    mbid = lookup_mbid(
        artist_name, mbid_cache, overrides=mbid_overrides, spotify_url=spotify_url
    )
    url = resolve_deezer_photo(artist_name, mbid, deezer_cache, deezer_overrides)
    if not url:
        return None
    return cache_deezer_artwork(url, dest, ttl_days, artist_label=artist_name)


# The artist's preferred image under artist_background_priority, read first by
# TrackSplit for its artist covers. Not "artist.jpg": TrackSplit writes its own
# artist.jpg cover into album folders.
PORTRAIT_FILE = "portrait.jpg"


def write_portrait(artist_dir: Path, priority: list[str]) -> Path | None:
    """Copy the chain's winning image to ``portrait.jpg``; None when there is none.

    An unchanged winner leaves the file untouched, so TrackSplit (which
    rebuilds a cover when its source's hash changes) does no needless work. A
    portrait whose sources are all gone is removed.
    """
    portrait = artist_dir / PORTRAIT_FILE
    source = preferred_artist_image(artist_dir, priority)
    if source is None:
        if portrait.exists():
            portrait.unlink()
            logger.debug("cache.portrait: status=removed dir=%s", artist_dir)
        return None
    data = source.read_bytes()
    if not portrait.exists() or portrait.read_bytes() != data:
        portrait.write_bytes(data)
        logger.debug(
            "cache.portrait: status=written dir=%s source=%s", artist_dir, source.name
        )
    return portrait


def refresh_artist_images(artists_root: Path, dj_cache, config) -> None:
    """Fetch every cached DJ's Deezer photo, then write each artist's portrait.

    Runs at the end of enrich, after the per-file steps, so TrackSplit finds
    a portrait for every artist even when no poster was regenerated. Deezer
    lookups are TTL-gated, so a repeat run makes no requests for artists
    already resolved.
    """
    priority = config.poster_settings["artist_background_priority"]
    if config.deezer_enabled and "deezer" in priority:
        from festival_organizer.deezer import DeezerCache, DeezerOverrides
        from festival_organizer.fanart import ArtistMbidOverrides, MBIDCache

        ttl = config.cache_ttl
        deps = {
            "mbid_cache": MBIDCache(ttl_days=ttl.get("mbid_days", 90)),
            "mbid_overrides": ArtistMbidOverrides(),
            "deezer_cache": DeezerCache(ttl_days=ttl.get("deezer_days", 90)),
            "deezer_overrides": DeezerOverrides(),
        }
        for slug in sorted(dj_cache.slugs()):
            fetch_deezer_artwork(
                dj_cache.canonical_name(slug),
                artists_root / folder_slug(slug) / ARTIST_IMAGE_FILES["deezer"],
                spotify_url=dj_cache.spotify_url(slug),
                ttl_days=ttl.get("images_days", 90),
                **deps,
            )
    if artists_root.is_dir():
        for artist_dir in sorted(p for p in artists_root.iterdir() if p.is_dir()):
            write_portrait(artist_dir, priority)


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
