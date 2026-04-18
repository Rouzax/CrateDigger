"""CLI handler for the 'identify' subcommand.

Logging:
    Logger: 'festival_organizer.tracklists.cli_handler'
    Key events:
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
    StepProgress,
    escape,
    header_panel,
    identify_summary_panel,
    make_console,
    results_table,
    suppression_enabled,
    verdict,
)
from festival_organizer.scanner import scan_folder
from festival_organizer.tracklists.api import (
    TracklistSession,
    TracklistError,
    AuthenticationError,
    RateLimitError,
    ExportError,
    top_genres_by_frequency,
)
from festival_organizer.mkv_tags import has_album_artist_display_tags, has_chapter_tags
from festival_organizer.tracklists.source_cache import SourceCache, SOURCE_TYPE_TO_TAG
from festival_organizer.tracklists.chapters import (
    parse_tracklist_lines,
    extract_existing_chapters,
    extract_stored_tracklist_info,
    chapters_are_identical,
    embed_chapters,
    trim_chapters_to_duration,
)
from festival_organizer.tracklists.query import (
    build_search_query,
    detect_tracklist_source,
    extract_tracklist_id,
    expand_aliases_in_query,
)
from festival_organizer.tracklists.scoring import parse_query, score_results


logger = logging.getLogger(__name__)

AUTO_SELECT_MIN_SCORE = 150
AUTO_SELECT_MIN_GAP = 20


def _build_search_expansion(config: Config) -> dict[str, str]:
    """Build {abbreviation: full_name} map for search query expansion.

    Only expands short uppercase abbreviations (AMF, ASOT, EDC) to their
    full names. Does not modify festivals.json or affect file naming.
    """
    expansion = {}
    for alias, canon in config.festival_aliases.items():
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
}


def _print_tagged_metadata_from_stored(filepath: Path, console: Console) -> None:
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
        console.print(f"  [dim]Tagged: {escape(', '.join(parts))}[/dim]")


def run_identify(args, config: Config, console: Console | None = None) -> int:
    """Main entry point for the 'identify' subcommand."""
    con = console or make_console()
    root = Path(args.root)
    auto_select = args.auto_select or config.tracklists_settings.get("auto_select", False)
    delay = args.delay if hasattr(args, "delay") and args.delay is not None else config.tracklists_settings.get("delay_seconds", 5)
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
        files = [f for f in scan_folder(root, config) if f.suffix.lower() in (".mkv", ".webm")]
        scan_root = root
    else:
        print(f"Error: path does not exist: {root}", file=sys.stderr)
        return 1

    if not files:
        print("No MKV/WEBM files found.")
        return 0

    # Get credentials and login
    from festival_organizer.tracklists.dj_cache import DjCache
    source_cache = SourceCache()
    dj_cache = DjCache()
    session = TracklistSession(source_cache=source_cache, dj_cache=dj_cache, delay=delay)
    email, password = _get_credentials(config)
    if not email or not password:
        print("Error: credentials required. Set TRACKLISTS_EMAIL and TRACKLISTS_PASSWORD environment variables.", file=sys.stderr)
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

        dj_name_set = dj_cache.all_names_lower() if dj_cache else set()
        dj_name_set |= {n.lower() for n in config.artist_aliases.keys()}
        dj_name_set |= {n.lower() for n in config.artist_aliases.values()}
        dj_name_set |= {g.lower() for g in config.artist_groups}

        source_name_set = source_cache.all_names_lower() if source_cache else set()
        source_name_set |= {n.lower() for n in config.known_festivals}

        # Process files
        stats = {"added": 0, "updated": 0, "up_to_date": 0, "skipped": 0,
                 "error": 0, "previewed": 0}
        tagged_festivals: dict[str, int] = {}
        unmatched_files: list[str] = []
        tagged_count = 0
        info_enabled = logger.isEnabledFor(logging.INFO)

        aborted = False
        for i, filepath in enumerate(files):
            if i > 0 and not preview:
                spinner.update(
                    f"[{i+1}/{len(files)}] Throttling {delay}s",
                    filename=filepath.name,
                )
                session.throttle()

            file_start = time.perf_counter()
            try:
                stat_key, vstatus, detail = _process_file(
                    filepath=filepath,
                    scan_root=scan_root,
                    session=session,
                    config=config,
                    source_cache=source_cache,
                    search_expansion=search_expansion,
                    dj_name_set=dj_name_set,
                    source_name_set=source_name_set,
                    tracklist_input=tracklist_input,
                    auto_select=auto_select,
                    ignore_stored=ignore_stored,
                    preview=preview,
                    quiet=quiet,
                    language=language,
                    console=con,
                    verbose=info_enabled,
                    spinner=spinner,
                    index=i + 1,
                    total=len(files),
                )
            except KeyboardInterrupt:
                spinner.stop()
                con.print("\nAborted by user.")
                aborted = True
                break
            except (TracklistError, AuthenticationError, RateLimitError, ExportError) as e:
                stat_key, vstatus, detail = "error", "error", f"{type(e).__name__}: {e}"
            except Exception as e:
                logger.exception("Unexpected error processing %s", filepath.name)
                stat_key, vstatus, detail = "error", "error", f"{type(e).__name__}: {e}"

            elapsed = time.perf_counter() - file_start
            stats[stat_key] = stats.get(stat_key, 0) + 1

            if stat_key in ("added", "updated", "up_to_date", "previewed"):
                stored = extract_stored_tracklist_info(filepath)
                fest = stored.get("festival", "") if stored else ""
                if fest:
                    tagged_festivals[fest] = tagged_festivals.get(fest, 0) + 1
                    tagged_count += 1
            elif stat_key == "skipped":
                stored = extract_stored_tracklist_info(filepath)
                if not stored or not stored.get("url"):
                    unmatched_files.append(filepath.name)
            elif stat_key == "error":
                unmatched_files.append(filepath.name)

            # Pause the spinner while we emit the verdict line so it doesn't
            # flicker over static output. Restart afterward for the next file.
            spinner.stop()
            console_width = con.size.width if con.size else 120
            con.print(verdict(
                status=vstatus, index=i + 1, total=len(files),
                filename=filepath.name, detail=detail, elapsed_s=elapsed,
                width=console_width,
            ))
            if info_enabled and stat_key in ("added", "updated"):
                _print_tagged_metadata_from_stored(filepath, con)
            spinner.start()

        if aborted:
            spinner.stop()

    total_elapsed = time.perf_counter() - total_start

    # Summary
    con.print()
    con.print(identify_summary_panel(
        stats=stats,
        tagged_count=tagged_count,
        festivals=tagged_festivals,
        unmatched=unmatched_files,
        elapsed_s=total_elapsed,
    ))

    return 0


def _process_file(
    filepath: Path,
    scan_root: Path,
    session: TracklistSession,
    config: Config,
    source_cache: SourceCache,
    search_expansion: dict[str, str],
    dj_name_set: set[str],
    source_name_set: set[str],
    tracklist_input: str | None,
    auto_select: bool,
    ignore_stored: bool,
    preview: bool,
    quiet: bool,
    language: str,
    console: Console | None = None,
    verbose: bool = False,
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

    # Check for stored tracklist URL
    if not ignore_stored:
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            if auto_select:
                if spinner is not None:
                    spinner.update(
                        f"[{index}/{total}] Verifying stored tracklist",
                        filename=filepath.name,
                    )
                return _fetch_and_embed(
                    session, stored["url"], filepath, duration_mins,
                    config, preview, quiet, language, console=con,
                    verbose=verbose, duration_seconds=mf.duration_seconds,
                    regenerate=ignore_stored,
                    spinner=spinner, index=index, total=total,
                )
            else:
                if spinner is not None:
                    spinner.stop()
                con.print(f"  [bold]Stored URL:[/bold] [dim]{escape(stored['url'])}[/dim]")
                choice = input("  Use stored? [Y]es / (S)kip / (R)esearch: ").strip().lower()
                con.print()
                if spinner is not None:
                    spinner.start()
                if choice in ("y", "yes", ""):
                    if spinner is not None:
                        spinner.update(
                            f"[{index}/{total}] Verifying stored tracklist",
                            filename=filepath.name,
                        )
                    return _fetch_and_embed(
                        session, stored["url"], filepath, duration_mins,
                        config, preview, quiet, language, console=con,
                        verbose=verbose, duration_seconds=mf.duration_seconds,
                        regenerate=ignore_stored,
                        spinner=spinner, index=index, total=total,
                    )
                elif choice in ("s", "skip"):
                    return ("skipped", "skipped", "user skipped")
                # else: fall through to search

    # Determine search query
    if tracklist_input:
        source = detect_tracklist_source(tracklist_input)
    else:
        query_str = build_search_query(filepath)
        source = {"type": "search", "value": query_str}

    # Handle direct URL or ID
    if source["type"] == "url":
        return _fetch_and_embed(
            session, source["value"], filepath, duration_mins,
            config, preview, quiet, language, console=con,
            verbose=verbose, duration_seconds=mf.duration_seconds,
            regenerate=ignore_stored,
            spinner=spinner, index=index, total=total,
        )
    elif source["type"] == "id":
        return _fetch_and_embed(
            session, None, filepath, duration_mins,
            config, preview, quiet, language, console=con,
            tracklist_id=source["value"],
            verbose=verbose, duration_seconds=mf.duration_seconds,
            regenerate=ignore_stored,
            spinner=spinner, index=index, total=total,
        )

    # Search
    query_str = source["value"]

    # Expand abbreviations for better 1001TL search results
    query_str = expand_aliases_in_query(query_str, search_expansion)

    if spinner is not None:
        spinner.update(f"[{index}/{total}] Searching 1001TL", filename=filepath.name)

    results = session.search(query_str, duration_minutes=duration_mins, year=mf.year or None)

    if not results:
        return ("skipped", "skipped", "no results")

    query_parts = parse_query(query_str, search_expansion)
    scored = score_results(results, query_parts, duration_mins,
                           dj_names=dj_name_set or None, source_names=source_name_set or None)

    if not scored:
        return ("skipped", "skipped", "no results")

    # Select result
    if auto_select:
        selected = scored[0]
        runner_up = scored[1].score if len(scored) > 1 else 0
        gap = selected.score - runner_up

        if selected.score < AUTO_SELECT_MIN_SCORE:
            return ("skipped", "skipped", f"low confidence (score {selected.score:.0f})")
        if gap < AUTO_SELECT_MIN_GAP:
            return ("skipped", "skipped", f"low confidence (gap {gap:.0f})")
    else:
        if spinner is not None:
            spinner.stop()
        selected = _select_interactive(scored, duration_mins, query_parts, con)
        if spinner is not None:
            spinner.start()
        if selected is None:
            return ("skipped", "skipped", "user cancelled")

    # Fetch and embed
    tl_id = selected.id
    return _fetch_and_embed(
        session, selected.url, filepath, duration_mins,
        config, preview, quiet, language, console=con,
        tracklist_id=tl_id,
        tracklist_date=selected.date,
        verbose=verbose, duration_seconds=mf.duration_seconds,
        regenerate=ignore_stored,
        spinner=spinner, index=index, total=total,
    )


def _fetch_and_embed(
    session: TracklistSession,
    url: str | None,
    filepath: Path,
    duration_mins: int,
    config: Config,
    preview: bool,
    quiet: bool,
    language: str,
    tracklist_id: str | None = None,
    tracklist_date: str | None = None,
    console: Console | None = None,
    verbose: bool = False,
    duration_seconds: float | None = None,
    regenerate: bool = False,
    spinner: StepProgress | None = None,
    index: int = 0,
    total: int = 0,
) -> tuple[str, str, str]:
    """Fetch tracklist, parse chapters, and embed.

    Returns a (stat_key, verdict_status, detail) triple.
    """
    con = console or make_console()

    if not tracklist_id and url:
        tracklist_id = extract_tracklist_id(url)

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

    # Cap the set-level GENRES tag per config. top_genres_by_frequency counts
    # per-track genre occurrences and keeps the top-N with deterministic
    # first-appearance tie-breaking. Fall back to the flat HTML scrape when
    # the per-track parser returned nothing (defensive: a 1001TL layout
    # change or an unparsed page still writes genres instead of an empty tag).
    genre_top_n = config.tracklists_settings.get("genre_top_n", 5)
    if genre_top_n and export.tracks:
        capped = top_genres_by_frequency(export.tracks, n=genre_top_n)
        set_genres = capped or list(export.genres)
    else:
        set_genres = list(export.genres)

    try:
        chapters = parse_tracklist_lines(export.lines, language=language)
        chapters = trim_chapters_to_duration(chapters, duration_seconds)
    except ValueError:
        if not preview:
            # Tag file with URL for future pickup
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=set_genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists, country=export.country, location=export.location, tracks=export.tracks, dj_cache=session._dj_cache, alias_resolver=config.resolve_artist)
        return ("skipped", "skipped", "no chapters parsed")

    if not chapters:
        return ("skipped", "skipped", "no chapters parsed")

    if len(chapters) < 2:
        if not preview:
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=set_genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists, country=export.country, location=export.location, tracks=export.tracks, dj_cache=session._dj_cache, alias_resolver=config.resolve_artist)
        return ("skipped", "skipped", "only 1 chapter")

    # Check for duplicates
    existing = extract_existing_chapters(filepath)
    if chapters_are_identical(existing, chapters):
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            # Chapters match. Decide whether a re-tag is needed.
            desired = {
                "CRATEDIGGER_1001TL_URL": export.url,
                "CRATEDIGGER_1001TL_TITLE": export.title,
                "CRATEDIGGER_1001TL_ID": tracklist_id or "",
                "CRATEDIGGER_1001TL_DATE": tracklist_date or "",
                "CRATEDIGGER_1001TL_GENRES": "|".join(set_genres) if set_genres else "",
                "CRATEDIGGER_1001TL_DJ_ARTWORK": export.dj_artwork_url,
            }
            if export.dj_artists:
                # See embed_chapters: this tag preserves the 1001TL display form;
                # alias resolution happens at the ARTIST (TTV=50) and filesystem
                # layout layer, not here.
                if session._dj_cache:
                    names = [session._dj_cache.canonical_name(slug, fallback=name)
                             for slug, name in export.dj_artists]
                else:
                    names = [name for _, name in export.dj_artists]
                desired["CRATEDIGGER_1001TL_ARTISTS"] = "|".join(names)
            if export.country:
                desired["CRATEDIGGER_1001TL_COUNTRY"] = export.country
            if export.location:
                desired["CRATEDIGGER_1001TL_LOCATION"] = export.location
            if export.source_type:
                desired["CRATEDIGGER_1001TL_SOURCE_TYPE"] = export.source_type
            if export.stage_text:
                desired["CRATEDIGGER_1001TL_STAGE"] = export.stage_text
            for source_type, names in export.sources_by_type.items():
                tag_name = SOURCE_TYPE_TO_TAG.get(source_type)
                if tag_name and names:
                    desired[tag_name] = "|".join(names)
            stored_map = {
                "CRATEDIGGER_1001TL_URL": stored.get("url", ""),
                "CRATEDIGGER_1001TL_TITLE": stored.get("title", ""),
                "CRATEDIGGER_1001TL_ID": stored.get("id", ""),
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
            }
            # Tags that would change at TTV=70
            tags_to_update = {
                k: v for k, v in desired.items()
                if v and v != stored_map.get(k, "")
            }
            # Self-heal: legacy files enriched before 0.9.9 lack TTV=30
            # per-chapter tags. Detect and route through the full embed path
            # so they get populated on next run without requiring a flag.
            missing_chapter_tags = not has_chapter_tags(filepath)
            # Second self-heal: files enriched before 0.12.4 only carry
            # CRATEDIGGER_1001TL_ARTISTS, not the companion _DISPLAY/_SLUGS
            # album-level tags. Force a re-embed using the stored URL so the
            # user doesn't have to --regenerate (which would re-search 1001TL
            # and risk rebinding to a different tracklist).
            missing_album_tags = bool(export.dj_artists) and not has_album_artist_display_tags(filepath)
            if (not tags_to_update and not missing_chapter_tags
                    and not missing_album_tags and not regenerate):
                return ("up_to_date", "up-to-date", f"{len(chapters)} chapters")
            # Otherwise route through embed_chapters: it writes TTV=70 +
            # per-chapter TTV=30 + folds any duplicate global Tag blocks.
            # Deterministic ChapterUIDs make this byte-idempotent on re-run.
            if missing_chapter_tags:
                reason = "populated per-chapter tags"
            elif missing_album_tags:
                reason = "populated album-artist tags"
            elif tags_to_update:
                friendly = ", ".join(
                    _FRIENDLY_TAG_NAMES.get(k, k) for k in tags_to_update
                )
                reason = f"updated {friendly}"
            else:
                reason = "refreshed (regenerate)"
            if preview:
                return ("updated", "updated", f"{export.title} . {reason} . {len(chapters)} chapters")
            if spinner is not None:
                spinner.update(
                    f"[{index}/{total}] Embedding {len(chapters)} chapters",
                    filename=filepath.name,
                )
            success = embed_chapters(
                filepath, chapters,
                tracklist_url=export.url, tracklist_title=export.title,
                tracklist_id=tracklist_id, tracklist_date=tracklist_date,
                genres=set_genres, dj_artwork_url=export.dj_artwork_url,
                stage_text=export.stage_text,
                sources_by_type=export.sources_by_type,
                dj_artists=export.dj_artists, country=export.country,
                location=export.location,
                tracks=export.tracks, dj_cache=session._dj_cache,
                alias_resolver=config.resolve_artist,
            )
            if success:
                return ("updated", "updated", f"{export.title} . {reason} . {len(chapters)} chapters")
            logger.warning("Failed to re-tag %s", filepath)
            return ("error", "error", "mkvpropedit failed")

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
    success = embed_chapters(filepath, chapters, tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=set_genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists, country=export.country, location=export.location, tracks=export.tracks, dj_cache=session._dj_cache, alias_resolver=config.resolve_artist)
    if success:
        return ("added", "done", f"{export.title} . {len(chapters)} chapters")
    return ("error", "error", "mkvpropedit failed")


def _select_interactive(results: list, duration_mins: int, query_parts=None, console: Console | None = None) -> object | None:
    """Display results table and prompt for selection."""
    con = console or make_console()

    con.print(f"\n  [bold]Search Results[/bold] [dim](video: {duration_mins}m)[/dim]")
    table = results_table(results, duration_mins, query_parts)
    con.print(table)
    con.print("   [dim]0. Cancel[/dim]\n")

    max_show = min(len(results), 15)
    selected: object | None = None
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
