"""Chapter XML generation, extraction, comparison, and embedding.

Handles Matroska chapter/tag XML for MKV files via mkvextract/mkvpropedit.

Logging:
    Logger: 'festival_organizer.tracklists.chapters'
    Key events:
        - chapters.extract_failed (DEBUG): Chapter extraction from MKV failed
        - chapters.embed_failed (DEBUG): Chapter or tag embedding failed
    See docs/logging.md for full guidelines.
"""
import hashlib
import logging
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, overload

from festival_organizer import metadata
from festival_organizer.mkv_tags import CLEAR_TAG, MATROSKA_EXTS, extract_all_tags, write_merged_tags
from festival_organizer.subprocess_utils import tracked_run
from festival_organizer.tracklists.source_cache import SOURCE_TYPE_TO_TAG

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from festival_organizer.tracklists.api import Track
    from festival_organizer.tracklists.dj_cache import DjCache


@dataclass
class Chapter:
    """A single chapter marker."""
    timestamp: str   # "HH:MM:SS.mmm"
    title: str
    language: str = "eng"


def _timestamp_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS.mmm timestamp to total seconds."""
    parts = ts.split(".")
    millis = int(parts[1]) if len(parts) > 1 else 0
    h, m, s = (int(x) for x in parts[0].split(":"))
    return h * 3600 + m * 60 + s + millis / 1000


MASHUP_THRESHOLD_SECONDS = 5


def normalize_timestamp(time_str: str) -> str:
    """Normalize a timestamp to HH:MM:SS.mmm format.

    Handles: mm:ss, m:ss, hh:mm:ss, hh:mm:ss.mmm, mm:ss.s
    """
    time_str = time_str.strip()
    millis = "000"

    # Extract milliseconds if present
    if "." in time_str:
        parts = time_str.rsplit(".", 1)
        time_str = parts[0]
        millis = parts[1].ljust(3, "0")[:3]

    segments = time_str.split(":")

    if len(segments) == 2:
        # mm:ss
        return f"00:{int(segments[0]):02d}:{int(segments[1]):02d}.{millis}"
    elif len(segments) == 3:
        # hh:mm:ss
        return f"{int(segments[0]):02d}:{int(segments[1]):02d}:{int(segments[2]):02d}.{millis}"
    else:
        raise ValueError(f"Invalid timestamp format: {time_str}")


def parse_tracklist_lines(lines: list[str], language: str = "eng") -> list[Chapter]:
    """Parse tracklist export lines into Chapter objects.

    Expected format: "[mm:ss] Track Title" or "[hh:mm:ss] Track Title"

    Chapters within MASHUP_THRESHOLD_SECONDS of each other are treated as
    mashup components; the earlier chapter is dropped and only the later one
    (the actual next track) is kept.

    Raises ValueError if lines contain numbered tracks but no timestamps
    (indicates tracklist exists but community hasn't added timestamps yet).
    """
    chapters = []
    has_numbered_tracks = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for timestamp pattern: [mm:ss] or [hh:mm:ss]
        match = re.match(r"^\s*\[([0-9:.]+)\]\s*(.+?)\s*$", line)
        if match:
            timestamp = normalize_timestamp(match.group(1))
            title = match.group(2)
            chapters.append(Chapter(timestamp=timestamp, title=title, language=language))
        elif re.match(r"^\s*\d+\.\s+", line):
            has_numbered_tracks = True

    if not chapters and has_numbered_tracks:
        raise ValueError("Tracklist has no timestamps yet (tracks are numbered but no time markers)")

    # Filter mashup components: when consecutive chapters are <threshold apart,
    # drop the earlier one (mashup marker) and keep the later one (actual track).
    if len(chapters) > 1:
        filtered = []
        for i, ch in enumerate(chapters):
            if i < len(chapters) - 1:
                gap = _timestamp_to_seconds(chapters[i + 1].timestamp) - _timestamp_to_seconds(ch.timestamp)
                if gap < MASHUP_THRESHOLD_SECONDS:
                    logger.info("Dropping mashup chapter: %s (%.0fs before next)", ch.title, gap)
                    continue
            filtered.append(ch)
        chapters = filtered

    return chapters


def trim_chapters_to_duration(
    chapters: list[Chapter],
    duration_s: float | None,
    epsilon: float = 2.0,
) -> list[Chapter]:
    """Drop chapters whose start is at or within epsilon of the media end.

    Tracklists from 1001TL describe the full DJ set, but the video file may be
    shorter (broadcast cuts, uploader trims). Chapters past the video's end
    would have zero duration in playback and confuse downstream tools like
    TrackSplit.

    Args:
        chapters: Chapter list from parse_tracklist_lines()
        duration_s: Media duration in seconds (e.g. MediaFile.duration_seconds).
            If None, no trimming happens.
        epsilon: Trim chapters starting within this many seconds of the end.

    Returns:
        New list of chapters with past-end entries removed. Logs at INFO when
        any chapters are dropped.
    """
    if duration_s is None:
        return chapters
    cutoff = duration_s - epsilon
    kept = [ch for ch in chapters if _timestamp_to_seconds(ch.timestamp) < cutoff]
    dropped = len(chapters) - len(kept)
    if dropped:
        logger.info(
            "Trimmed %d chapters past video end (duration=%.1fs)",
            dropped, duration_s,
        )
    return kept


@overload
def build_chapter_xml(chapters: list[Chapter], return_uids: Literal[False] = False) -> str: ...
@overload
def build_chapter_xml(chapters: list[Chapter], return_uids: Literal[True]) -> tuple[str, list[int]]: ...
def build_chapter_xml(chapters: list[Chapter], return_uids: bool = False):
    """Generate Matroska chapter XML string.

    When return_uids=True, returns (xml_str, uids) where uids[i] is the
    ChapterUID assigned to chapters[i]. Callers that want to emit per-chapter
    tags targeting those UIDs use the tuple form; all existing callers that
    just write chapter XML keep getting a bare string.
    """
    root = ET.Element("Chapters")
    edition = ET.SubElement(root, "EditionEntry")
    uids: list[int] = []

    for ch in chapters:
        atom = ET.SubElement(edition, "ChapterAtom")
        # Deterministic ChapterUID: hash (timestamp, title) to a stable 64-bit
        # value so re-enrichment produces byte-identical chapter XML (and the
        # TTV=30 tags that reference these UIDs) when the source data is
        # unchanged. Matroska requires ChapterUID > 0; MD5 of non-empty input
        # is never zero in practice.
        digest = hashlib.md5(f"{ch.timestamp}|{ch.title}".encode("utf-8")).digest()
        uid_value = int.from_bytes(digest[:8], "big") or 1
        uids.append(uid_value)
        uid = ET.SubElement(atom, "ChapterUID")
        uid.text = str(uid_value)

        time_start = ET.SubElement(atom, "ChapterTimeStart")
        time_start.text = ch.timestamp

        display = ET.SubElement(atom, "ChapterDisplay")
        ch_string = ET.SubElement(display, "ChapterString")
        ch_string.text = ch.title
        ch_lang = ET.SubElement(display, "ChapterLanguage")
        ch_lang.text = ch.language

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    if return_uids:
        return xml_str, uids
    return xml_str



def extract_existing_chapters(filepath: Path) -> list[Chapter] | None:
    """Extract chapters from an MKV file via mkvextract.

    Returns list of Chapter objects, or None if no chapters or tool unavailable.
    """
    if not metadata.MKVEXTRACT_PATH:
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w") as f:
            xml_path = f.name

        result = tracked_run(
            [metadata.MKVEXTRACT_PATH, str(filepath), "chapters", xml_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        if result.returncode != 0 or not os.path.exists(xml_path):
            return None

        # Check if file has content
        content = Path(xml_path).read_text(encoding="utf-8").strip()
        if not content:
            return None

        tree = ET.parse(xml_path)
        root = tree.getroot()

        chapters = []
        for atom in root.iter("ChapterAtom"):
            time_elem = atom.find("ChapterTimeStart")
            display = atom.find("ChapterDisplay")
            if time_elem is not None and display is not None:
                title_elem = display.find("ChapterString")
                lang_elem = display.find("ChapterLanguage")
                timestamp = time_elem.text or ""
                # Normalize nanosecond timestamps to milliseconds
                if len(timestamp) > 12:
                    timestamp = timestamp[:12]
                title = title_elem.text if title_elem is not None else ""
                language = lang_elem.text if lang_elem is not None else "eng"
                chapters.append(Chapter(timestamp=timestamp, title=title, language=language))

        return chapters if chapters else None

    except (OSError, subprocess.SubprocessError, ET.ParseError) as e:
        logger.debug("Chapter extraction failed for %s: %s", filepath, e)
        return None
    finally:
        try:
            os.unlink(xml_path)
        except OSError:
            pass


def extract_stored_tracklist_info(filepath: Path) -> dict | None:
    """Extract stored 1001TL tags from MKV file.

    Returns dict with all 1001TL tag values, or None if no tags found.
    """
    root = extract_all_tags(filepath)
    if root is None:
        return None

    tag_map = {
        # New names (preferred)
        "CRATEDIGGER_1001TL_URL": "url",
        "CRATEDIGGER_1001TL_TITLE": "title",
        "CRATEDIGGER_1001TL_ID": "id",
        "CRATEDIGGER_1001TL_DATE": "date",
        "CRATEDIGGER_1001TL_GENRES": "genres",
        "CRATEDIGGER_1001TL_DJ_ARTWORK": "dj_artwork",
        "CRATEDIGGER_1001TL_STAGE": "stage",
        "CRATEDIGGER_1001TL_VENUE": "venue",
        "CRATEDIGGER_1001TL_FESTIVAL": "festival",
        "CRATEDIGGER_1001TL_CONFERENCE": "conference",
        "CRATEDIGGER_1001TL_RADIO": "radio",
        "CRATEDIGGER_1001TL_ARTISTS": "artists",
        "CRATEDIGGER_1001TL_COUNTRY": "country",
        "CRATEDIGGER_1001TL_LOCATION": "location",
        "CRATEDIGGER_1001TL_SOURCE_TYPE": "source_type",
        # Old names (backward compatibility)
        "1001TRACKLISTS_URL": "url",
        "1001TRACKLISTS_TITLE": "title",
        "1001TRACKLISTS_ID": "id",
        "1001TRACKLISTS_DATE": "date",
        "1001TRACKLISTS_GENRES": "genres",
        "1001TRACKLISTS_DJ_ARTWORK": "dj_artwork",
    }
    result = {v: "" for v in tag_map.values()}

    for tag in root.iter("Tag"):
        targets = tag.find("Targets")
        if targets is not None:
            ttv = targets.find("TargetTypeValue")
            if ttv is not None and int(ttv.text or "0") < 70:
                continue

        for simple in tag.iter("Simple"):
            name = simple.find("Name")
            string = simple.find("String")
            if name is not None and string is not None and name.text in tag_map:
                result[tag_map[name.text]] = string.text or ""

    if any(result.values()):
        return result
    return None


def chapters_are_identical(existing: list[Chapter] | None, new: list[Chapter]) -> bool:
    """Compare two chapter lists for equality.

    Compares count, timestamps (to mm:ss precision), and titles.
    """
    if existing is None:
        return False
    if len(existing) != len(new):
        return False

    for e, n in zip(existing, new):
        # Compare timestamps to mm:ss precision (ignore milliseconds)
        e_short = e.timestamp[:8] if len(e.timestamp) >= 8 else e.timestamp
        n_short = n.timestamp[:8] if len(n.timestamp) >= 8 else n.timestamp
        if e_short != n_short:
            return False
        if e.title != n.title:
            return False

    return True


def _build_chapter_tags_map(
    chapters: list[Chapter],
    chapter_uids: list[int],
    tracks: list["Track"],
    dj_cache: "DjCache | None",
    alias_resolver: "Callable[[str], str] | None" = None,
) -> dict[int, dict[str, str]]:
    """Match each chapter to a track by exact start_ms; build TTV=30 tag map.

    chapters[i] pairs with chapter_uids[i]. For each chapter we look up a
    Track whose start_ms equals the chapter's timestamp-in-ms. Unmatched
    chapters produce no tag block. The returned dict is keyed by ChapterUID.

    PERFORMER names resolve via DjCache, then through alias_resolver
    (typically Config.resolve_artist) so per-chapter names match the
    canonicalised top-level ARTIST tag.
    """
    tracks_by_ms: dict[int, "Track"] = {}
    for t in tracks:
        tracks_by_ms.setdefault(t.start_ms, t)  # first wins on ties
    result: dict[int, dict[str, str]] = {}
    for chapter, uid in zip(chapters, chapter_uids):
        chapter_ms = int(_timestamp_to_seconds(chapter.timestamp) * 1000)
        track = tracks_by_ms.get(chapter_ms)
        if track is None:
            continue
        entry: dict[str, str] = {}
        if track.artist_slugs:
            # CrateDigger-prefixed per-chapter names avoid mediainfo's
            # flattening behavior: standard Matroska slot names (PERFORMER,
            # LABEL, GENRE) at TTV=30 get promoted into mediainfo's General
            # section (last-wins), making files look like they carry the
            # last chapter's artist/label at file level. Prefixed names are
            # unknown to mediainfo so they stay scoped where we put them.
            entry["CRATEDIGGER_TRACK_PERFORMER_SLUGS"] = "|".join(track.artist_slugs)
            # Length must match CRATEDIGGER_TRACK_PERFORMER_SLUGS: enrich zips SLUGS/NAMES/MBIDS by index.
            if track.artist_names and len(track.artist_names) == len(track.artist_slugs):
                entry["CRATEDIGGER_TRACK_PERFORMER_NAMES"] = "|".join(track.artist_names)
            # CRATEDIGGER_TRACK_PERFORMER is the full artist display line
            # exactly as 1001TL renders it: everything before the final
            # " - " in raw_text. Covers solo ("AFROJACK ft. Eva Simons"),
            # multi-artist ("Fred again.. & Jamie T"), and mashup composites
            # ("NLW & MureKian vs. ... vs. RÜFÜS DU SOL") in one rule.
            # Alias resolution is deliberately NOT applied here: this tag
            # preserves the 1001TL display form so players can show what the
            # DJ / crowd knows the track as. Alias -> canonical substitution
            # (e.g. SOMETHING ELSE -> ALOK) is only for filesystem routing
            # and happens at the top-level ARTIST tag, not here.
            if " - " in track.raw_text:
                display = track.raw_text.rsplit(" - ", 1)[0].strip()
            else:
                display = track.raw_text.strip() or track.artist_slugs[0]
            entry["CRATEDIGGER_TRACK_PERFORMER"] = display
        if track.title:
            # TITLE is kept as-is: Matroska's standard per-chapter name and
            # not subject to mediainfo's General-section flattening for
            # video files (the ChapterString already drives chapter display).
            entry["TITLE"] = track.title
        if track.label:
            entry["CRATEDIGGER_TRACK_LABEL"] = track.label
        if track.genres:
            entry["CRATEDIGGER_TRACK_GENRE"] = "|".join(track.genres)
        if entry:
            result[uid] = entry
    return result


def embed_chapters(
    filepath: Path,
    chapters: list[Chapter],
    tracklist_url: str | None = None,
    tracklist_title: str | None = None,
    tracklist_id: str | None = None,
    tracklist_date: str | None = None,
    genres: list[str] | None = None,
    dj_artwork_url: str | None = None,
    stage_text: str = "",
    sources_by_type: dict[str, list[str]] | None = None,
    dj_artists: list[tuple[str, str]] | None = None,
    country: str = "",
    location: str = "",
    tracks: list["Track"] | None = None,
    dj_cache: "DjCache | None" = None,
    alias_resolver: "Callable[[str], str] | None" = None,
) -> bool:
    """Write chapters and optional tags to an MKV file.

    Chapters: written via mkvpropedit --chapters (replaces chapters only, safe).
    Tags: written via extract-merge-write to preserve existing tags.

    Returns True on success, False on failure.
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not filepath.exists() or filepath.suffix.lower() not in MATROSKA_EXTS:
        return False

    chapter_file = None
    chapter_uids: list[int] = []

    try:
        # Write chapters via mkvpropedit --chapters (only if chapters provided)
        if chapters:
            chapter_xml, chapter_uids = build_chapter_xml(chapters, return_uids=True)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(chapter_xml)
                chapter_file = f.name

            result = tracked_run(
                [metadata.MKVPROPEDIT_PATH, str(filepath), "--chapters", chapter_file],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )

            if result.returncode != 0:
                return False

        # Write 1001TL tags via merge (preserves ARTIST/TITLE/DATE etc.)
        if tracklist_url:
            tags: dict[str, str] = {"CRATEDIGGER_1001TL_URL": tracklist_url}
            if tracklist_title:
                tags["CRATEDIGGER_1001TL_TITLE"] = tracklist_title
            if tracklist_id:
                tags["CRATEDIGGER_1001TL_ID"] = tracklist_id
            if tracklist_date:
                tags["CRATEDIGGER_1001TL_DATE"] = tracklist_date
            if genres:
                tags["CRATEDIGGER_1001TL_GENRES"] = "|".join(genres)
            if dj_artwork_url:
                tags["CRATEDIGGER_1001TL_DJ_ARTWORK"] = dj_artwork_url
            if stage_text:
                tags["CRATEDIGGER_1001TL_STAGE"] = stage_text
            if sources_by_type:
                for source_type, names in sources_by_type.items():
                    tag_name = SOURCE_TYPE_TO_TAG.get(source_type)
                    if tag_name and names:
                        tags[tag_name] = "|".join(names)
            if country:
                tags["CRATEDIGGER_1001TL_COUNTRY"] = country
            # CRATEDIGGER_1001TL_LOCATION is a lowest-tier fallback derived
            # from the 1001TL h1 plain-text tail. It only applies when no
            # linked location-bearing source (Festival / Venue / Conference /
            # Radio) is present. When such a source IS present, any stale
            # LOCATION tag from a prior run must be cleared so the file
            # doesn't carry a contradictory freeform value.
            LOCATION_BEARING_TAGS = (
                "CRATEDIGGER_1001TL_FESTIVAL",
                "CRATEDIGGER_1001TL_VENUE",
                "CRATEDIGGER_1001TL_CONFERENCE",
                "CRATEDIGGER_1001TL_RADIO",
            )
            linked_source_tag_present = any(t in tags for t in LOCATION_BEARING_TAGS)
            if location and not linked_source_tag_present:
                tags["CRATEDIGGER_1001TL_LOCATION"] = location
            elif linked_source_tag_present:
                tags["CRATEDIGGER_1001TL_LOCATION"] = CLEAR_TAG
            # TODO: source_type priority is also derived in api.py export_tracklist().
            # Consider passing source_type as a parameter instead of re-deriving.
            for stype in ("Open Air / Festival", "Event Location", "Club",
                          "Conference", "Concert / Live Event", "Event Promoter"):
                if sources_by_type and stype in sources_by_type:
                    tags["CRATEDIGGER_1001TL_SOURCE_TYPE"] = stype
                    break
            if dj_artists:
                # CRATEDIGGER_1001TL_ARTISTS preserves the 1001TL display form
                # (e.g. 'SOMETHING ELSE'). The top-level ARTIST tag and the
                # filesystem layout route through alias resolution separately;
                # this tag is the raw 1001TL-stated DJ name, casing-normalised
                # via DjCache (so we don't re-emit 1001TL's UPPERCASE-on-submit
                # artefact when DjCache has the canonical casing).
                names = [
                    dj_cache.canonical_name(slug, fallback=name) if dj_cache is not None else name
                    for slug, name in dj_artists
                ]
                slugs = [slug for slug, _name in dj_artists]
                tags["CRATEDIGGER_1001TL_ARTISTS"] = "|".join(names)
                tags["CRATEDIGGER_ALBUMARTIST_SLUGS"] = "|".join(slugs)
                tags["CRATEDIGGER_ALBUMARTIST_DISPLAY"] = " & ".join(names)
            chapter_tags: dict[int, dict[str, str]] | None = None
            if tracks and chapters and chapter_uids:
                chapter_tags = _build_chapter_tags_map(
                    chapters, chapter_uids, tracks, dj_cache, alias_resolver
                )
            return write_merged_tags(filepath, {70: tags}, chapter_tags=chapter_tags)

        return True

    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Chapter embedding failed for %s: %s", filepath, e)
        return False
    finally:
        if chapter_file:
            try:
                os.unlink(chapter_file)
            except OSError:
                pass
