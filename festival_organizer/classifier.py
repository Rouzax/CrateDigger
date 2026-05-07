"""Content type classification: festival_set vs concert_film.

Logging:
    Logger: 'festival_organizer.classifier'
    Key events:
        - classifier.result (INFO): Classification result for each file
    See docs/logging.md for full guidelines.
"""
import logging
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile

logger = logging.getLogger(__name__)


def classify(media_file: MediaFile, root: Path, config: Config) -> str:
    """Determine the content type of a media file.

    Returns: "festival_set", "concert_film", or "unknown".

    Priority:
    1. Config force_concert / force_festival patterns (explicit user override)
    2. Has 1001TRACKLISTS_TITLE -> festival_set
    3. Known festival detected -> festival_set
    4. Fallback -> unknown
    """
    # Compute relative path for pattern matching
    try:
        rel = str(media_file.source_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = media_file.source_path.name

    # 1. Explicit user overrides
    if config.is_forced_concert(rel):
        logger.info("classifier.result: file=%s type=concert_film reason=config_forced", media_file.source_path.name)
        return "concert_film"
    if config.is_forced_festival(rel):
        logger.info("classifier.result: file=%s type=festival_set reason=config_forced", media_file.source_path.name)
        return "festival_set"

    # 2. Has 1001TL metadata -> festival
    if media_file.metadata_source == "1001tracklists":
        logger.info("classifier.result: file=%s type=festival_set reason=1001tracklists_metadata", media_file.source_path.name)
        return "festival_set"

    # 3. Has a known festival name -> festival (resolve aliases first)
    if media_file.festival:
        canonical = config.resolve_place_alias(media_file.festival)
        if canonical in config.known_places:
            logger.info("classifier.result: file=%s type=festival_set reason=known_festival festival=%s", media_file.source_path.name, canonical)
            return "festival_set"

    # 4. Fallback
    logger.info("classifier.result: file=%s type=unknown", media_file.source_path.name)
    return "unknown"
