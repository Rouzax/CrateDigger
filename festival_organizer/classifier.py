"""Content type classification: festival_set vs concert_film.

Logging:
    Logger: 'festival_organizer.classifier'
    Key events:
        - classify.result (INFO): Classification result for each file
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
        logger.info("Classified as concert_film (forced by config)")
        return "concert_film"
    if config.is_forced_festival(rel):
        logger.info("Classified as festival_set (forced by config)")
        return "festival_set"

    # 2. Has 1001TL metadata -> festival
    if media_file.metadata_source == "1001tracklists":
        logger.info("Classified as festival_set (1001tracklists metadata)")
        return "festival_set"

    # 3. Has a known festival name -> festival
    if media_file.festival and media_file.festival in config.known_festivals:
        logger.info("Classified as festival_set (known festival: %s)", media_file.festival)
        return "festival_set"

    # 4. Fallback
    logger.info("Classified as unknown")
    return "unknown"
