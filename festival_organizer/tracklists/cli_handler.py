"""CLI handler for the 'identify' subcommand.

Logging:
    Logger: 'festival_organizer.tracklists.cli_handler'
    Key events:
        - identify.stored_url (INFO): Stored URL decision (reuse/skip/research)
        - identify.direct_input (DEBUG): Direct URL or ID supplied
        - identify.youtube_lookup (INFO): Watch-URL lookup resolved tracklist(s) by embedded video id (with hit count)
        - identify.search (INFO): Search query dispatched (with optional alias expansion)
        - identify.results (DEBUG): Scored result count and top scores
        - identify.auto_select (INFO): Auto-select accept or reject with reason
        - identify.fetch (INFO): Tracklist fetch initiated
        - identify.player.match (INFO): Multi-source tracklist; selected the source matching this file (by yt_id or duration)
        - identify.player.no_match (WARNING): Multi-source tracklist; no source matched this file, so metadata is written but chapters are skipped
        - identify.skip (DEBUG): Early return before embed (parse_failed/no_chapters/single_chapter)
        - identify.chapters_match (DEBUG): Chapter identity comparison result
        - identify.chapters_no_stored (DEBUG): Chapters match but no stored tags found
        - identify.tags_update (DEBUG): Tag diff computed (changed count and names)
        - identify.self_heal (DEBUG): Legacy self-heal triggered (missing_chapter_tags/missing_album_tags)
        - identify.regenerate (DEBUG): Forced re-embed via --regenerate
        - identify.write_failed (WARNING): Tag writing via mkvpropedit failed
    See docs/logging.md for full guidelines.
"""

import logging
import re
import sys
import time
from pathlib import Path

from rich.console import Console

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import Config
from festival_organizer.console import (
    VERDICT_BADGE_WIDTH,
    StepProgress,
    escape,
    header_panel,
    identify_summary_panel,
    make_console,
    results_table,
    suppression_enabled,
    verdict,
)
from festival_organizer.log import _file_var
from festival_organizer.mkv_tags import (
    CLEAR_TAG,
    has_album_artist_display_tags,
    has_chapter_tags,
    has_legacy_chapter_title,
)
from festival_organizer.scanner import scan_folder
from festival_organizer.tracklists.api import (
    AuthenticationError,
    ExportError,
    RateLimitError,
    Track,
    TracklistError,
    TracklistSession,
    top_genres_by_frequency,
)
from festival_organizer.tracklists.chapters import (
    Chapter,
    _ms_to_timestamp,
    build_1001tl_tags,
    chapters_are_identical,
    embed_chapters,
    extract_existing_chapters,
    extract_stored_tracklist_info,
    parse_tracklist_lines,
    strip_chapter_label,
    supplement_chapters_from_tracks,
)
from festival_organizer.tracklists.overlays import assemble
from festival_organizer.tracklists.players import (
    partition_lines_by_player,
    select_player,
)
from festival_organizer.tracklists.query import (
    build_search_query,
    detect_tracklist_source,
    expand_aliases_in_query,
    extract_tracklist_id,
)
from festival_organizer.tracklists.scoring import (
    SearchResult,
    parse_query,
    score_results,
)
from festival_organizer.tracklists.source_cache import SourceCache

logger = logging.getLogger(__name__)

AUTO_SELECT_MIN_SCORE = 150
AUTO_SELECT_MIN_GAP = 20


def _build_search_expansion(config: Config) -> dict[str, str]:
    """Build {abbreviation: full_name} map for search query expansion.

    Only expands short uppercase abbreviations (AMF, ASOT, EDC) to their
    full names. Does not modify places.json or affect file naming.
    """
    expansion = {}
    for alias, canon in config.place_aliases.items():
        if alias == canon:
            continue
        short, long = (canon, alias) if len(canon) < len(alias) else (alias, canon)
        if re.match(r"^[A-Z]{2,6}$", short):
            key = short.lower()
            if key not in expansion or len(long) > len(expansion[key]):
                expansion[key] = long
    return expansion


_FRIENDLY_TAG_NAMES = {
    "CRATEDIGGER_1001TL_URL": "url",
    "CRATEDIGGER_1001TL_TITLE": "title",
    "CRATEDIGGER_1001TL_ID": "id",
    "CRATEDIGGER_1001TL_YOUTUBE_ID": "youtube id",
    "CRATEDIGGER_1001TL_DATE": "date",
    "CRATEDIGGER_1001TL_GENRES": "genres",
    "CRATEDIGGER_1001TL_DJ_ARTWORK": "dj artwork",
    "CRATEDIGGER_1001TL_STAGE": "stage",
    "CRATEDIGGER_1001TL_VENUE": "venue",
    "CRATEDIGGER_1001TL_FESTIVAL": "festival",
    "CRATEDIGGER_1001TL_CONFERENCE": "conference",
    "CRATEDIGGER_1001TL_RADIO": "radio",
    "CRATEDIGGER_1001TL_ARTISTS": "artists",
    "CRATEDIGGER_1001TL_COUNTRY": "country",
    "CRATEDIGGER_1001TL_LOCATION": "location",
    "CRATEDIGGER_1001TL_SOURCE_TYPE": "source type",
    "CRATEDIGGER_ALBUMARTIST_SLUGS": "artist slugs",
    "CRATEDIGGER_ALBUMARTIST_DISPLAY": "artist display",
}


def _youtube_lookup(
    session: TracklistSession,
    filepath: Path,
    file_youtube_id: str,
) -> list[SearchResult]:
    """Resolve a tracklist from a file's embedded YouTube id.

    1001TL resolves a YouTube watch-URL query to the tracklist(s) linked to
    that exact video. Returns the search results (possibly empty). Empty when
    the file carries no id, so callers fall back to text search.
    """
    if not file_youtube_id:
        return []
    results = session.search(f"https://www.youtube.com/watch?v={file_youtube_id}")
    if results:
        logger.info(
            "identify.youtube_lookup: file=%s yt_id=%s hits=%d",
            filepath.name,
            file_youtube_id,
            len(results),
        )
    return results


def _print_tagged_metadata_from_stored(
    filepath: Path,
    console: Console,
    *,
    total: int = 0,
) -> None:
    """Print per-file tagged metadata from stored tags (post-verdict, under --verbose).

    Reads tags with extract_stored_tracklist_info instead of consuming a live
    TracklistExport object. Use when the export isn't on hand.
    """
    stored = extract_stored_tracklist_info(filepath)
    if not stored:
        return
    parts = []
    if stored.get("artists"):
        parts.append(stored["artists"].replace("|", ", "))
    for key in ("festival", "conference", "radio"):
        val = stored.get(key, "")
        if val:
            parts.append(val.split("|")[0])
            break
    if stored.get("stage"):
        parts.append(stored["stage"])
    if parts:
        iw = len(str(total)) if total else 1
        indent = VERDICT_BADGE_WIDTH + 2 * iw + 4
        console.print(f"{' ' * indent}[dim]Tagged: {escape(', '.join(parts))}[/dim]")


def run_identify(args, config: Config, console: Console | None = None) -> int:
    """Main entry point for the 'identify' subcommand."""
    con = console or make_console()
    root = Path(args.root)
    auto_select = args.auto_select or config.tracklists_settings.get(
        "auto_select", False
    )
    delay = (
        args.delay
        if hasattr(args, "delay") and args.delay is not None
        else config.tracklists_settings.get("delay_seconds", 5)
    )
    preview = getattr(args, "preview", False)
    ignore_stored = getattr(args, "ignore_stored_url", False)
    tracklist_input = getattr(args, "tracklist", None)
    quiet = getattr(args, "quiet", False)
    language = config.tracklists_settings.get("chapter_language", "eng")

    suppressed = suppression_enabled(
        con,
        quiet=quiet,
        verbose=getattr(args, "verbose", False),
        debug=getattr(args, "debug", False),
    )

    # Determine files to process
    if root.is_file():
        files = [root]
        scan_root = root.parent
    elif root.is_dir():
        files = [
            f
            for f in scan_folder(root, config)
            if f.suffix.lower() in (".mkv", ".webm")
        ]
        scan_root = root
    else:
        print(f"Error: path does not exist: {root}", file=sys.stderr)
        return 1

    if not files:
        print("No MKV/WEBM files found.")
        return 0

    # Get credentials and login
    source_cache = SourceCache()
    dj_cache = config.dj_cache
    session = TracklistSession(source_cache=source_cache, dj_cache=dj_cache)
    email, password = _get_credentials(config)
    if not email or not password:
        print(
            "Error: credentials required. Set TRACKLISTS_EMAIL and TRACKLISTS_PASSWORD environment variables.",
            file=sys.stderr,
        )
        return 1

    total_start = time.perf_counter()

    with StepProgress(con, enabled=not suppressed) as spinner:
        spinner.update("Signing in to 1001Tracklists...")
        try:
            session.login(email, password)
        except AuthenticationError as e:
            spinner.stop()
            print(f"Login failed: {e}", file=sys.stderr)
            return 1

        rows = {
            "Source": str(root),
            "Files": str(len(files)),
            "Mode": "preview" if preview else "embed",
            "Select": "auto" if auto_select else "interactive",
        }
        spinner.stop()
        con.print(header_panel("CrateDigger: Identify", rows))
        spinner.start()

        # Pre-compute search expansion and name sets (constant across all files)
        search_expansion = _build_search_expansion(config)

        # Process files
        stats = {
            "updated": 0,
            "up_to_date": 0,
            "skipped": 0,
            "error": 0,
            "previewed": 0,
        }
        tagged_festivals: dict[str, int] = {}
        unmatched_files: list[str] = []
        updated_paths: list[Path] = []
        tagged_count = 0
        info_enabled = logger.isEnabledFor(logging.INFO)

        aborted = False
        # Anchor inter-file pacing on when the previous file's processing
        # began, not on the last 1001TL request. That way time spent in the
        # interactive selection menu (and any per-file API work) counts
        # toward the delay, and a file that already ran longer than `delay`
        # adds no extra wait before the next file starts.
        prev_file_start: float | None = None
        for i, filepath in enumerate(files):
            _file_var.set(filepath.name)
            if prev_file_start is not None and not preview:
                remaining = delay - (time.monotonic() - prev_file_start)
                if remaining > 0:
                    spinner.update(
                        f"[{i + 1}/{len(files)}] Cooling down {remaining:.1f}s",
                        filename=filepath.name,
                    )
                    time.sleep(remaining)

            prev_file_start = time.monotonic()
            file_start = time.perf_counter()
            try:
                stat_key, vstatus, detail = _process_file(
                    filepath=filepath,
                    scan_root=scan_root,
                    session=session,
                    config=config,
                    search_expansion=search_expansion,
                    tracklist_input=tracklist_input,
                    auto_select=auto_select,
                    ignore_stored=ignore_stored,
                    preview=preview,
                    quiet=quiet,
                    language=language,
                    console=con,
                    spinner=spinner,
                    index=i + 1,
                    total=len(files),
                )
            except KeyboardInterrupt:
                spinner.stop()
                con.print("\nAborted by user.")
                aborted = True
                break
            except (
                TracklistError,
                AuthenticationError,
                RateLimitError,
                ExportError,
            ) as e:
                stat_key, vstatus, detail = "error", "error", f"{type(e).__name__}: {e}"
            except Exception as e:
                logger.exception("Unexpected error processing %s", filepath.name)
                stat_key, vstatus, detail = "error", "error", f"{type(e).__name__}: {e}"

            elapsed = time.perf_counter() - file_start
            stats[stat_key] = stats.get(stat_key, 0) + 1

            if stat_key == "updated":
                updated_paths.append(filepath)

            if stat_key in ("updated", "up_to_date", "previewed"):
                tagged_count += 1
                stored = extract_stored_tracklist_info(filepath)
                fest = stored.get("festival", "") if stored else ""
                if fest:
                    tagged_festivals[fest] = tagged_festivals.get(fest, 0) + 1
            elif stat_key == "skipped":
                stored = extract_stored_tracklist_info(filepath)
                if not stored or not stored.get("url"):
                    unmatched_files.append(filepath.name)
            elif stat_key == "error":
                unmatched_files.append(filepath.name)

            console_width = con.size.width if con.size else 120
            con.print(
                verdict(
                    status=vstatus,
                    index=i + 1,
                    total=len(files),
                    filename=filepath.name,
                    detail_line=detail if detail else None,
                    elapsed_s=elapsed,
                    width=console_width,
                )
            )
            if info_enabled and stat_key == "updated":
                _print_tagged_metadata_from_stored(filepath, con, total=len(files))

        if aborted:
            spinner.stop()

    total_elapsed = time.perf_counter() - total_start

    # Summary
    con.print()
    con.print(
        identify_summary_panel(
            stats=stats,
            tagged_count=tagged_count,
            festivals=tagged_festivals,
            unmatched=unmatched_files,
            elapsed_s=total_elapsed,
        )
    )

    from festival_organizer import notify

    def _count_chapters(path):
        try:
            chapters = extract_existing_chapters(path)
            return len(chapters) if chapters else None
        except Exception:
            return None

    def _analyse(path):
        return analyse_file(path, scan_root, config)

    notify.notify_updated_sets(
        config,
        updated_paths=updated_paths,
        analyse=_analyse,
        count_chapters=_count_chapters,
        flag=getattr(args, "email", None),
        run_stats=stats,
        console=con,
        suppressed=suppressed,
    )

    return 0


def _process_file(
    filepath: Path,
    scan_root: Path,
    session: TracklistSession,
    config: Config,
    search_expansion: dict[str, str],
    tracklist_input: str | None,
    auto_select: bool,
    ignore_stored: bool,
    preview: bool,
    quiet: bool,
    language: str,
    console: Console | None = None,
    spinner: StepProgress | None = None,
    index: int = 0,
    total: int = 0,
) -> tuple[str, str, str]:
    """Process a single file. Returns a (stat_key, verdict_status, detail) triple."""
    con = console or make_console()

    if spinner is not None:
        spinner.update(f"[{index}/{total}] Analysing", filename=filepath.name)

    # Analyse file for metadata
    mf = analyse_file(filepath, scan_root, config)
    mf.content_type = classify(mf, scan_root, config)
    duration_mins = int(mf.duration_seconds / 60) if mf.duration_seconds else 0
    # Source id for this file: the [id] filename suffix on fresh downloads, or
    # the persisted CRATEDIGGER_1001TL_YOUTUBE_ID tag on renamed/organized
    # files (analyzer falls back to the tag). Lets a re-run recover its source
    # player by id, or fall through to duration matching when absent.
    file_youtube_id = mf.youtube_id

    # Check for stored tracklist URL
    if not ignore_stored:
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            if auto_select:
                logger.info(
                    "identify.stored_url: file=%s url=%s action=reuse",
                    filepath.name,
                    stored["url"],
                )
                if spinner is not None:
                    spinner.update(
                        f"[{index}/{total}] Verifying stored tracklist",
                        filename=filepath.name,
                    )
                return _fetch_and_embed(
                    session,
                    stored["url"],
                    filepath,
                    config,
                    preview,
                    quiet,
                    language,
                    console=con,
                    duration_seconds=mf.duration_seconds,
                    regenerate=ignore_stored,
                    spinner=spinner,
                    index=index,
                    total=total,
                    youtube_id=file_youtube_id,
                )
            else:
                if spinner is not None:
                    spinner.stop()
                con.print()
                if total > 0:
                    con.print(
                        f"  [bold]\\[{index}/{total}][/bold] {escape(filepath.name)}"
                    )
                else:
                    con.print(f"  {escape(filepath.name)}")
                con.print(
                    f"  [bold]Stored URL:[/bold] [dim]{escape(stored['url'])}[/dim]"
                )
                choice = (
                    input("  Use stored? [Y]es / (S)kip / (R)esearch: ").strip().lower()
                )
                con.print()
                if spinner is not None:
                    spinner.start()
                if choice in ("y", "yes", ""):
                    logger.info(
                        "identify.stored_url: file=%s url=%s action=reuse",
                        filepath.name,
                        stored["url"],
                    )
                    if spinner is not None:
                        spinner.update(
                            f"[{index}/{total}] Verifying stored tracklist",
                            filename=filepath.name,
                        )
                    return _fetch_and_embed(
                        session,
                        stored["url"],
                        filepath,
                        config,
                        preview,
                        quiet,
                        language,
                        console=con,
                        duration_seconds=mf.duration_seconds,
                        regenerate=ignore_stored,
                        spinner=spinner,
                        index=index,
                        total=total,
                        youtube_id=file_youtube_id,
                    )
                elif choice in ("s", "skip"):
                    logger.info(
                        "identify.stored_url: file=%s url=%s action=skip",
                        filepath.name,
                        stored["url"],
                    )
                    return ("skipped", "skipped", "user skipped")
                else:
                    logger.info(
                        "identify.stored_url: file=%s url=%s action=research",
                        filepath.name,
                        stored["url"],
                    )
                # fall through to search

    # Determine search query
    if tracklist_input:
        source = detect_tracklist_source(tracklist_input)
    else:
        # Anchor on the file's embedded YouTube id first: a watch-URL query lets
        # 1001TL resolve the exact tracklist(s) linked to that video. Seeds the
        # candidate set so both auto and interactive selection apply.
        yt_results = _youtube_lookup(session, filepath, file_youtube_id)
        if len(yt_results) == 1:
            # Unambiguous video match: behave like a pasted URL/ID (bypass picker)
            top = yt_results[0]
            return _fetch_and_embed(
                session,
                top.url,
                filepath,
                config,
                preview,
                quiet,
                language,
                tracklist_id=top.id,
                tracklist_date=top.date,
                console=con,
                duration_seconds=mf.duration_seconds,
                regenerate=ignore_stored,
                spinner=spinner,
                index=index,
                total=total,
                youtube_id=file_youtube_id,
            )
        if len(yt_results) > 1:
            # Several tracklists carry this video: let scoring + selection choose,
            # but only among the video-anchored candidates.
            results = yt_results
            source = {"type": "search", "value": "", "prescored": True}
        else:
            query_str = build_search_query(filepath)
            source = {"type": "search", "value": query_str}

    # Handle direct URL or ID
    if source["type"] == "url":
        logger.debug(
            "identify.direct_input: file=%s type=url value=%s",
            filepath.name,
            source["value"],
        )
        return _fetch_and_embed(
            session,
            source["value"],
            filepath,
            config,
            preview,
            quiet,
            language,
            console=con,
            duration_seconds=mf.duration_seconds,
            regenerate=ignore_stored,
            spinner=spinner,
            index=index,
            total=total,
            youtube_id=file_youtube_id,
        )
    elif source["type"] == "id":
        logger.debug(
            "identify.direct_input: file=%s type=id value=%s",
            filepath.name,
            source["value"],
        )
        return _fetch_and_embed(
            session,
            None,
            filepath,
            config,
            preview,
            quiet,
            language,
            console=con,
            tracklist_id=source["value"],
            duration_seconds=mf.duration_seconds,
            regenerate=ignore_stored,
            spinner=spinner,
            index=index,
            total=total,
            youtube_id=file_youtube_id,
        )

    # Search
    if source.get("prescored"):
        # Candidates already seeded by the YouTube watch-URL lookup. Derive the
        # scoring/display query from the filename so the existing ranking and
        # interactive table still apply among the video-anchored candidates.
        query_str = expand_aliases_in_query(
            build_search_query(filepath), search_expansion
        )
    else:
        original_query = source["value"]

        # Expand abbreviations for better 1001TL search results
        query_str = expand_aliases_in_query(original_query, search_expansion)

        if query_str != original_query:
            logger.info(
                'identify.search: file=%s query="%s" expanded="%s" duration_m=%d year=%s',
                filepath.name,
                original_query,
                query_str,
                duration_mins,
                mf.year or "",
            )
        else:
            logger.info(
                'identify.search: file=%s query="%s" duration_m=%d year=%s',
                filepath.name,
                query_str,
                duration_mins,
                mf.year or "",
            )

        if spinner is not None:
            spinner.update(
                f"[{index}/{total}] Searching 1001TL", filename=filepath.name
            )

        results = session.search(
            query_str, duration_minutes=duration_mins, year=mf.year or None
        )

    if not results:
        return ("skipped", "skipped", "no results")

    query_parts = parse_query(query_str, search_expansion)
    scored = score_results(results, query_parts, duration_mins)

    if not scored:
        return ("skipped", "skipped", "no results")

    logger.debug(
        "identify.results: file=%s count=%d top_score=%.0f runner_up=%.0f",
        filepath.name,
        len(scored),
        scored[0].score if scored else 0,
        scored[1].score if len(scored) > 1 else 0,
    )

    # Select result
    if auto_select:
        selected = scored[0]
        runner_up = scored[1].score if len(scored) > 1 else 0
        gap = selected.score - runner_up

        if selected.score < AUTO_SELECT_MIN_SCORE:
            logger.info(
                "identify.auto_select: file=%s action=reject reason=low_score score=%.0f min=%d",
                filepath.name,
                selected.score,
                AUTO_SELECT_MIN_SCORE,
            )
            return (
                "skipped",
                "skipped",
                f"low confidence (score {selected.score:.0f})",
            )
        if gap < AUTO_SELECT_MIN_GAP:
            logger.info(
                "identify.auto_select: file=%s action=reject reason=low_gap score=%.0f gap=%.0f min=%d",
                filepath.name,
                selected.score,
                gap,
                AUTO_SELECT_MIN_GAP,
            )
            return ("skipped", "skipped", f"low confidence (gap {gap:.0f})")
        logger.info(
            "identify.auto_select: file=%s action=accept score=%.0f gap=%.0f id=%s",
            filepath.name,
            selected.score,
            gap,
            selected.id,
        )
    else:
        if spinner is not None:
            spinner.stop()
        selected = _select_interactive(
            scored,
            duration_mins,
            query_parts,
            con,
            filename=filepath.name,
            query_str=query_str,
            index=index,
            total=total,
        )
        if spinner is not None:
            spinner.start()
        if selected is None:
            return ("skipped", "skipped", "user cancelled")

    # Fetch and embed
    tl_id = selected.id
    return _fetch_and_embed(
        session,
        selected.url,
        filepath,
        config,
        preview,
        quiet,
        language,
        console=con,
        tracklist_id=tl_id,
        tracklist_date=selected.date,
        duration_seconds=mf.duration_seconds,
        regenerate=ignore_stored,
        spinner=spinner,
        index=index,
        total=total,
        youtube_id=file_youtube_id,
    )


def _fetch_and_embed(
    session: TracklistSession,
    url: str | None,
    filepath: Path,
    config: Config,
    preview: bool,
    quiet: bool,
    language: str,
    tracklist_id: str | None = None,
    tracklist_date: str | None = None,
    console: Console | None = None,
    duration_seconds: float | None = None,
    regenerate: bool = False,
    spinner: StepProgress | None = None,
    index: int = 0,
    total: int = 0,
    youtube_id: str | None = None,
) -> tuple[str, str, str]:
    """Fetch tracklist, parse chapters, and embed.

    Returns a (stat_key, verdict_status, detail) triple.
    """
    con = console or make_console()

    if not tracklist_id and url:
        tracklist_id = extract_tracklist_id(url)

    logger.info("identify.fetch: file=%s id=%s", filepath.name, tracklist_id or "")

    if spinner is not None:
        spinner.update(
            f"[{index}/{total}] Fetching tracklist",
            filename=filepath.name,
        )
        export = session.export_tracklist(
            tracklist_id,
            full_url=url,
            on_progress=lambda msg: spinner.update(
                f"[{index}/{total}] {msg}", filename=filepath.name
            ),
        )
    else:
        export = session.export_tracklist(tracklist_id, full_url=url)

    # When the search-results date is absent (or this is a stored-URL
    # re-enrichment that never carried one), fall back to the event date
    # captured from the h1 tail so CRATEDIGGER_1001TL_DATE still gets written
    # instead of ceding to the YouTube DATE tag at display time.
    effective_date = tracklist_date or export.date or None

    # (b) Persist the source id for ANY matched source (single or multi),
    # duration-confirmed inside select_player so we never write a guessed id.
    matched_ordinal = select_player(export.players, youtube_id, duration_seconds)
    persisted_youtube_id = ""
    if matched_ordinal:  # >= 1 means a confirmed source match
        persisted_youtube_id = export.players[matched_ordinal - 1].youtube_id

    # (a) Multi-source tracklists cue tracks against more than one video.
    # Keep only the source that matches this file; refuse to chapter when no
    # source matches (would otherwise embed another video's timeline).
    # Single-source tracklists are unaffected (chapter the whole timeline).
    selected_player = 0
    is_multiplayer = len(export.players) >= 2
    if is_multiplayer:
        if matched_ordinal is None:
            logger.warning(
                "identify.player.no_match: file=%s players=%d yt_id=%s dur=%.0f",
                filepath.name,
                len(export.players),
                youtube_id or "",
                duration_seconds or 0,
            )
            if not preview:
                embed_chapters(
                    filepath,
                    [],  # empty -> embed_chapters leaves existing chapters intact
                    tracklist_url=export.url,
                    tracklist_title=export.title,
                    tracklist_id=tracklist_id,
                    tracklist_date=effective_date,
                    genres=list(export.genres),
                    dj_artwork_url=export.dj_artwork_url,
                    stage_text=export.stage_text,
                    sources_by_type=export.sources_by_type,
                    dj_artists=export.dj_artists,
                    country=export.country,
                    location=export.location,
                    tracks=export.tracks,
                    dj_cache=session._dj_cache,
                    alias_resolver=config.resolve_artist,
                    youtube_id=persisted_youtube_id,
                )
            return ("skipped", "skipped", "no matching player")
        selected_player = matched_ordinal
        logger.info(
            "identify.player.match: file=%s player=%d yt_id=%s",
            filepath.name,
            selected_player,
            persisted_youtube_id or youtube_id or "",
        )

    # Scope tracks and lines to the selected source. Only multi-source
    # selection narrows them; single-source keeps the full timeline.
    if selected_player:  # only set for multi-source matches
        export_tracks = [t for t in export.tracks if t.player == selected_player]
        export_lines = partition_lines_by_player(export.lines).get(selected_player, [])
    else:
        export_tracks = export.tracks
        export_lines = export.lines

    # Cap the set-level GENRES tag per config. top_genres_by_frequency counts
    # per-track genre occurrences and keeps the top-N with deterministic
    # first-appearance tie-breaking. Fall back to the flat HTML scrape when
    # the per-track parser returned nothing (defensive: a 1001TL layout
    # change or an unparsed page still writes genres instead of an empty tag).
    genre_top_n = config.tracklists_settings.get("genre_top_n", 5)
    capped: list[str] = []
    if genre_top_n and export_tracks:
        capped = top_genres_by_frequency(export_tracks, n=genre_top_n)
        set_genres = capped or list(export.genres)
    else:
        set_genres = list(export.genres)
    if set_genres:
        source = "frequency" if capped else "scrape"
        logger.info(
            "identify.genres: file=%s written=%d scraped=%d source=%s genres=%s",
            filepath.name,
            len(set_genres),
            len(export.genres),
            source,
            "|".join(set_genres),
        )

    try:
        anchors = parse_tracklist_lines(export_lines, language=language)
        anchors = supplement_chapters_from_tracks(
            anchors, export_tracks, language=language
        )
    except ValueError:
        logger.debug("identify.skip: file=%s reason=parse_failed", filepath.name)
        if not preview:
            # Tag file with URL for future pickup
            embed_chapters(
                filepath,
                [],
                tracklist_url=export.url,
                tracklist_title=export.title,
                tracklist_id=tracklist_id,
                tracklist_date=effective_date,
                genres=set_genres,
                dj_artwork_url=export.dj_artwork_url,
                stage_text=export.stage_text,
                sources_by_type=export.sources_by_type,
                dj_artists=export.dj_artists,
                country=export.country,
                location=export.location,
                tracks=export_tracks,
                dj_cache=session._dj_cache,
                alias_resolver=config.resolve_artist,
                youtube_id=persisted_youtube_id,
            )
        return ("skipped", "skipped", "no chapters parsed")

    # Assemble overlay ("w/") chapters on top of the anchor chapters, then trim
    # to the media duration and derive the final Chapter list. With
    # overlay_chapters off, assemble (fold_seconds=None) returns one chapter per
    # anchor but still attaches a mashup main's tlpSubTog sub-components as
    # contributors, so mashup metadata can still be harvested. assembled and
    # chapters stay aligned 1:1 (same order/length) for the per-chapter tag merge.
    anchor_tracks: dict[int, Track] = {}
    for t in export_tracks:
        if not t.is_overlay and not t.is_subcomponent:
            anchor_tracks.setdefault(t.start_ms, t)
    fold = config.overlay_fold_seconds if config.overlay_chapters else None
    assembled = assemble(anchors, anchor_tracks, export_tracks, fold_seconds=fold)

    # Drop assembled chapters at or within 2.0s of the media end
    # (cutoff = duration - epsilon, epsilon 2.0s).
    if duration_seconds is not None:
        cutoff = duration_seconds - 2.0
        kept = [ac for ac in assembled if ac.start_ms / 1000.0 < cutoff]
        dropped = len(assembled) - len(kept)
        if dropped:
            logger.info(
                "chapters.trim: dropped=%d duration=%.1fs",
                dropped,
                duration_seconds,
            )
        assembled = kept

    chapters = [
        Chapter(
            timestamp=_ms_to_timestamp(ac.start_ms),
            title=(
                ac.title
                if config.chapter_title_labels
                else strip_chapter_label(ac.title)
            ),
            language=ac.language,
        )
        for ac in assembled
    ]

    if not chapters:
        logger.debug("identify.skip: file=%s reason=no_chapters", filepath.name)
        return ("skipped", "skipped", "no chapters parsed")

    if len(chapters) < 2:
        logger.debug(
            "identify.skip: file=%s reason=single_chapter chapters=%d",
            filepath.name,
            len(chapters),
        )
        if not preview:
            embed_chapters(
                filepath,
                [],
                tracklist_url=export.url,
                tracklist_title=export.title,
                tracklist_id=tracklist_id,
                tracklist_date=effective_date,
                genres=set_genres,
                dj_artwork_url=export.dj_artwork_url,
                stage_text=export.stage_text,
                sources_by_type=export.sources_by_type,
                dj_artists=export.dj_artists,
                country=export.country,
                location=export.location,
                tracks=export_tracks,
                dj_cache=session._dj_cache,
                alias_resolver=config.resolve_artist,
                youtube_id=persisted_youtube_id,
            )
        return ("skipped", "skipped", "only 1 chapter")

    # Check for duplicates
    existing = extract_existing_chapters(filepath)
    match = chapters_are_identical(existing, chapters)
    logger.debug(
        "identify.chapters_match: file=%s match=%s existing=%d new=%d",
        filepath.name,
        match,
        len(existing) if existing else 0,
        len(chapters),
    )
    if match:
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            # Chapters match. Decide whether a re-tag is needed.
            desired = build_1001tl_tags(
                tracklist_url=export.url,
                tracklist_title=export.title,
                tracklist_id=tracklist_id or "",
                youtube_id=persisted_youtube_id,
                tracklist_date=effective_date or "",
                genres=set_genres,
                dj_artwork_url=export.dj_artwork_url,
                stage_text=export.stage_text,
                sources_by_type=export.sources_by_type,
                country=export.country,
                location=export.location,
                dj_artists=export.dj_artists,
                dj_cache=session._dj_cache,
            )
            stored_map = {
                "CRATEDIGGER_1001TL_URL": stored.get("url", ""),
                "CRATEDIGGER_1001TL_TITLE": stored.get("title", ""),
                "CRATEDIGGER_1001TL_ID": stored.get("id", ""),
                "CRATEDIGGER_1001TL_YOUTUBE_ID": stored.get("youtube_id", ""),
                "CRATEDIGGER_1001TL_DATE": stored.get("date", ""),
                "CRATEDIGGER_1001TL_GENRES": stored.get("genres", ""),
                "CRATEDIGGER_1001TL_DJ_ARTWORK": stored.get("dj_artwork", ""),
                "CRATEDIGGER_1001TL_STAGE": stored.get("stage", ""),
                "CRATEDIGGER_1001TL_VENUE": stored.get("venue", ""),
                "CRATEDIGGER_1001TL_FESTIVAL": stored.get("festival", ""),
                "CRATEDIGGER_1001TL_CONFERENCE": stored.get("conference", ""),
                "CRATEDIGGER_1001TL_RADIO": stored.get("radio", ""),
                "CRATEDIGGER_1001TL_ARTISTS": stored.get("artists", ""),
                "CRATEDIGGER_1001TL_COUNTRY": stored.get("country", ""),
                "CRATEDIGGER_1001TL_LOCATION": stored.get("location", ""),
                "CRATEDIGGER_1001TL_SOURCE_TYPE": stored.get("source_type", ""),
                "CRATEDIGGER_ALBUMARTIST_SLUGS": stored.get("albumartist_slugs", ""),
                "CRATEDIGGER_ALBUMARTIST_DISPLAY": stored.get(
                    "albumartist_display", ""
                ),
            }
            # Tags that would change at TTV=70
            tags_to_update: dict[str, str] = {}
            for k, v in desired.items():
                stored_val = stored_map.get(k, "")
                if v is CLEAR_TAG:
                    if stored_val:
                        tags_to_update[k] = v
                elif v and v != stored_val:
                    tags_to_update[k] = v
            if tags_to_update:
                friendly = ", ".join(
                    _FRIENDLY_TAG_NAMES.get(k, k) for k in tags_to_update
                )
                logger.debug(
                    "identify.tags_update: file=%s changed=%d tags=%s",
                    filepath.name,
                    len(tags_to_update),
                    friendly,
                )
            else:
                logger.debug("identify.tags_update: file=%s changed=0", filepath.name)
            # Self-heal: legacy files enriched before 0.9.9 lack TTV=30
            # per-chapter tags. Detect and route through the full embed path
            # so they get populated on next run without requiring a flag.
            missing_chapter_tags = not has_chapter_tags(filepath)
            # Second self-heal: files enriched before 0.12.4 only carry
            # CRATEDIGGER_1001TL_ARTISTS, not the companion _DISPLAY/_SLUGS
            # album-level tags. Force a re-embed using the stored URL so the
            # user doesn't have to --regenerate (which would re-search 1001TL
            # and risk rebinding to a different tracklist).
            missing_album_tags = bool(
                export.dj_artists
            ) and not has_album_artist_display_tags(filepath)
            legacy_chapter_title = has_legacy_chapter_title(filepath)
            if missing_chapter_tags:
                logger.debug(
                    "identify.self_heal: file=%s reason=missing_chapter_tags",
                    filepath.name,
                )
            elif missing_album_tags:
                logger.debug(
                    "identify.self_heal: file=%s reason=missing_album_tags",
                    filepath.name,
                )
            elif legacy_chapter_title:
                logger.debug(
                    "identify.self_heal: file=%s reason=legacy_chapter_title",
                    filepath.name,
                )
            if (
                not tags_to_update
                and not missing_chapter_tags
                and not missing_album_tags
                and not legacy_chapter_title
                and not regenerate
            ):
                return ("up_to_date", "up-to-date", "")
            # Otherwise route through embed_chapters: it writes TTV=70 +
            # per-chapter TTV=30 + folds any duplicate global Tag blocks.
            # Deterministic ChapterUIDs make this byte-idempotent on re-run.
            if missing_chapter_tags:
                reason = "populated per-chapter tags"
            elif missing_album_tags:
                reason = "populated album-artist tags"
            elif legacy_chapter_title:
                reason = "renamed legacy TITLE to CRATEDIGGER_TRACK_TITLE"
            elif tags_to_update:
                friendly = ", ".join(
                    _FRIENDLY_TAG_NAMES.get(k, k) for k in tags_to_update
                )
                reason = f"updated {friendly}"
            else:
                reason = "refreshed (regenerate)"
                logger.debug("identify.regenerate: file=%s", filepath.name)
            if preview:
                return (
                    "updated",
                    "updated",
                    f"{export.title} . {reason} . {len(chapters)} chapters",
                )
            if spinner is not None:
                spinner.update(
                    f"[{index}/{total}] Embedding {len(chapters)} chapters",
                    filename=filepath.name,
                )
            success = embed_chapters(
                filepath,
                chapters,
                tracklist_url=export.url,
                tracklist_title=export.title,
                tracklist_id=tracklist_id,
                tracklist_date=effective_date,
                genres=set_genres,
                dj_artwork_url=export.dj_artwork_url,
                stage_text=export.stage_text,
                sources_by_type=export.sources_by_type,
                dj_artists=export.dj_artists,
                country=export.country,
                location=export.location,
                tracks=export_tracks,
                dj_cache=session._dj_cache,
                alias_resolver=config.resolve_artist,
                youtube_id=persisted_youtube_id,
                assembled=assembled,
                mashup_metadata=config.mashup_metadata,
            )
            if success:
                return (
                    "updated",
                    "updated",
                    f"{export.title} . {reason} . {len(chapters)} chapters",
                )
            logger.warning("identify.retag: status=failed file=%s", filepath)
            return ("error", "error", "mkvpropedit failed")
        else:
            logger.debug(
                "identify.chapters_no_stored: file=%s existing=%d",
                filepath.name,
                len(existing) if existing else 0,
            )

    # Preview-only: show the planned chapter list, don't write.
    if preview:
        if not quiet:
            con.print(f"  [bold]Tracklist:[/bold] {escape(export.title)}")
            con.print(f"  [bold]Chapters:[/bold]  {len(chapters)}")
            for ch in chapters:
                con.print(f"    [dim]{ch.timestamp[:8]}[/dim] {escape(ch.title)}")
        return ("previewed", "preview", f"{export.title} . {len(chapters)} chapters")

    # Embed
    if spinner is not None:
        spinner.update(
            f"[{index}/{total}] Embedding {len(chapters)} chapters",
            filename=filepath.name,
        )
    success = embed_chapters(
        filepath,
        chapters,
        tracklist_url=export.url,
        tracklist_title=export.title,
        tracklist_id=tracklist_id,
        tracklist_date=effective_date,
        genres=set_genres,
        dj_artwork_url=export.dj_artwork_url,
        stage_text=export.stage_text,
        sources_by_type=export.sources_by_type,
        dj_artists=export.dj_artists,
        country=export.country,
        location=export.location,
        tracks=export_tracks,
        dj_cache=session._dj_cache,
        alias_resolver=config.resolve_artist,
        youtube_id=persisted_youtube_id,
        assembled=assembled,
        mashup_metadata=config.mashup_metadata,
    )
    if success:
        return ("updated", "updated", f"{export.title} . {len(chapters)} chapters")
    return ("error", "error", "mkvpropedit failed")


def _select_interactive(
    results: list[SearchResult],
    duration_mins: int,
    query_parts=None,
    console: Console | None = None,
    *,
    filename: str | None = None,
    query_str: str | None = None,
    index: int = 0,
    total: int = 0,
) -> SearchResult | None:
    """Display results table and prompt for selection."""
    con = console or make_console()

    con.print()
    if filename:
        if total > 0:
            con.print(f"  [bold]\\[{index}/{total}][/bold] {escape(filename)}")
        else:
            con.print(f"  {escape(filename)}")
    if query_str:
        con.print(f"  [dim]Query:[/dim] {escape(query_str)}")
    con.print(f"  [bold]Search Results[/bold] [dim](video: {duration_mins}m)[/dim]")
    table = results_table(results, duration_mins, query_parts)
    con.print(table)
    con.print("   [dim]0. Cancel[/dim]\n")

    max_show = min(len(results), 15)
    selected: SearchResult | None = None
    while True:
        try:
            choice = input(f"  Select (1-{max_show}, or 0): ").strip()
            if not choice:
                continue
            num = int(choice)
            if num == 0:
                selected = None
                break
            if 1 <= num <= max_show:
                selected = results[num - 1]
                break
        except ValueError:
            con.print(f"  [dim]Enter a number (1-{max_show}) or 0 to skip[/dim]")
            continue
        except EOFError:
            selected = None
            break
    # Emit a trailing newline so the next print starts on a fresh line.
    con.print()
    return selected


def _get_credentials(config: Config) -> tuple[str, str]:
    """Get 1001Tracklists credentials from config or interactive prompt."""
    email, password = config.tracklists_credentials

    if not email:
        try:
            email = input("1001Tracklists email: ").strip()
            password = input("1001Tracklists password: ").strip()
        except (EOFError, KeyboardInterrupt):
            pass

    return email, password
