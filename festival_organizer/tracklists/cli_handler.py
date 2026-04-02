"""CLI handler for the 'identify' subcommand."""
import logging
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.text import Text

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import Config
from festival_organizer.console import (
    escape,
    header_panel,
    make_console,
    results_table,
    summary_panel,
)
from festival_organizer.scanner import scan_folder
from festival_organizer.tracklists.api import (
    TracklistSession,
    TracklistError,
    AuthenticationError,
    RateLimitError,
    ExportError,
)
from festival_organizer.mkv_tags import write_merged_tags
from festival_organizer.tracklists.source_cache import SourceCache, SOURCE_TYPE_TO_TAG
from festival_organizer.tracklists.chapters import (
    parse_tracklist_lines,
    extract_existing_chapters,
    extract_stored_tracklist_info,
    chapters_are_identical,
    embed_chapters,
)
from festival_organizer.tracklists.query import (
    build_search_query,
    detect_tracklist_source,
    extract_tracklist_id,
    expand_aliases_in_query,
)
from festival_organizer.tracklists.scoring import parse_query, score_results


logger = logging.getLogger(__name__)

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
}


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

    try:
        session.login(email, password)
    except AuthenticationError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1

    rows = {
        "Source": str(root),
        "Files": str(len(files)),
        "Mode": "preview" if preview else "embed",
        "Select": "auto" if auto_select else "interactive",
    }
    con.print(header_panel("CrateDigger: Identify", rows))

    # Process files
    stats = {"added": 0, "updated": 0, "up_to_date": 0, "skipped": 0, "error": 0}

    for i, filepath in enumerate(files):
        if i > 0 and not preview:
            time.sleep(delay)

        if not quiet:
            text = Text()
            text.append(f"\n[{i+1}/{len(files)}] ", style="bold")
            text.append(filepath.name)
            con.print(text)

        try:
            status = _process_file(
                filepath=filepath,
                scan_root=scan_root,
                session=session,
                config=config,
                source_cache=source_cache,
                tracklist_input=tracklist_input,
                auto_select=auto_select,
                ignore_stored=ignore_stored,
                preview=preview,
                quiet=quiet,
                language=language,
                console=con,
            )
            stats[status] = stats.get(status, 0) + 1
        except KeyboardInterrupt:
            con.print("\nAborted by user.")
            break
        except Exception as e:
            con.print(f"  [red]Error:[/red] {escape(str(e))}")
            stats["error"] += 1

    # Summary
    con.print()
    con.print(summary_panel(stats))

    return 0


def _process_file(
    filepath: Path,
    scan_root: Path,
    session: TracklistSession,
    config: Config,
    source_cache: SourceCache,
    tracklist_input: str | None,
    auto_select: bool,
    ignore_stored: bool,
    preview: bool,
    quiet: bool,
    language: str,
    console: Console | None = None,
) -> str:
    """Process a single file. Returns status string."""
    con = console or make_console()

    # Analyse file for metadata
    mf = analyse_file(filepath, scan_root, config)
    mf.content_type = classify(mf, scan_root, config)
    duration_mins = int(mf.duration_seconds / 60) if mf.duration_seconds else 0

    # Check for stored tracklist URL
    if not ignore_stored:
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            if auto_select:
                con.print(f"  [bold]Stored URL:[/bold] [dim]{escape(stored['url'])}[/dim]")
                return _fetch_and_embed(
                    session, stored["url"], filepath, duration_mins,
                    config, preview, quiet, language, console=con,
                )
            else:
                con.print(f"  [bold]Stored URL:[/bold] [dim]{escape(stored['url'])}[/dim]")
                choice = input("  Use stored? [Y]es / (S)kip / (R)esearch: ").strip().lower()
                if choice in ("y", "yes", ""):
                    return _fetch_and_embed(
                        session, stored["url"], filepath, duration_mins,
                        config, preview, quiet, language, console=con,
                    )
                elif choice in ("s", "skip"):
                    return "skipped"
                # else: fall through to search

    # Determine search query
    if tracklist_input:
        source = detect_tracklist_source(tracklist_input)
    else:
        query_str = build_search_query(filepath)
        source = {"type": "search", "value": query_str}

    # Handle direct URL or ID
    if source["type"] == "url":
        tl_id = extract_tracklist_id(source["value"])
        return _fetch_and_embed(
            session, source["value"], filepath, duration_mins,
            config, preview, quiet, language, console=con,
        )
    elif source["type"] == "id":
        return _fetch_and_embed(
            session, None, filepath, duration_mins,
            config, preview, quiet, language, console=con,
            tracklist_id=source["value"],
        )

    # Search
    query_str = source["value"]

    # Expand known abbreviations for better API results (AMF -> Amsterdam Music Festival)
    search_aliases = {alias.lower(): canon for alias, canon in config.festival_aliases.items()
                      if alias != canon}
    query_str = expand_aliases_in_query(query_str, search_aliases)

    if not quiet:
        con.print(f"  [bold]Query:[/bold] {escape(query_str)}")

    results = session.search(query_str, duration_minutes=duration_mins, year=mf.year or None)

    if not results:
        con.print("  [dim]No results found.[/dim]")
        return "skipped"

    # Score results (aliases already loaded above)
    query_parts = parse_query(query_str, search_aliases)
    scored = score_results(results, query_parts, duration_mins)

    if not scored:
        con.print("  [dim]No relevant results after filtering.[/dim]")
        return "skipped"

    # Select result
    if auto_select:
        selected = scored[0]
        if not quiet:
            _display_auto_selected(selected, duration_mins, con)
    else:
        selected = _select_interactive(scored, duration_mins, query_parts, con)
        if selected is None:
            return "skipped"

    # Fetch and embed
    tl_id = selected.id
    return _fetch_and_embed(
        session, selected.url, filepath, duration_mins,
        config, preview, quiet, language, console=con,
        tracklist_id=tl_id,
        tracklist_date=selected.date,
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
) -> str:
    """Fetch tracklist, parse chapters, and embed."""
    con = console or make_console()

    if not tracklist_id and url:
        tracklist_id = extract_tracklist_id(url)

    export = session.export_tracklist(tracklist_id, full_url=url)

    try:
        chapters = parse_tracklist_lines(export.lines, language=language)
    except ValueError as e:
        con.print(f"  {escape(str(e))}")
        if not preview:
            # Tag file with URL for future pickup
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists)
            con.print("  Tagged with URL for future pickup.")
        return "skipped"

    if not chapters:
        con.print("  [dim]No chapters found in tracklist.[/dim]")
        return "skipped"

    if len(chapters) < 2:
        con.print("  [dim]Only 1 chapter, skipping (not useful for navigation)[/dim]")
        if not preview:
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists)
            con.print("  Tagged with URL for future pickup.")
        return "skipped"

    # Check for duplicates
    existing = extract_existing_chapters(filepath)
    if chapters_are_identical(existing, chapters):
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            # Chapters match, check if tags need updating
            desired = {
                "CRATEDIGGER_1001TL_URL": export.url,
                "CRATEDIGGER_1001TL_TITLE": export.title,
                "CRATEDIGGER_1001TL_ID": tracklist_id or "",
                "CRATEDIGGER_1001TL_DATE": tracklist_date or "",
                "CRATEDIGGER_1001TL_GENRES": "|".join(export.genres) if export.genres else "",
                "CRATEDIGGER_1001TL_DJ_ARTWORK": export.dj_artwork_url,
            }
            if export.dj_artists:
                desired["CRATEDIGGER_1001TL_ARTISTS"] = "|".join(name for _, name in export.dj_artists)
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
            }
            # Only update tags that have a new non-empty value different from stored
            tags_to_update = {
                k: v for k, v in desired.items()
                if v and v != stored_map.get(k, "")
            }
            if not tags_to_update:
                if not quiet:
                    con.print(f"  [green]Up to date[/green] ({len(chapters)} chapters)")
                return "up_to_date"
            # Re-embed only the changed tags, skip chapter writing
            if not preview:
                if write_merged_tags(filepath, {70: tags_to_update}):
                    if not quiet:
                        friendly = ", ".join(
                            _FRIENDLY_TAG_NAMES.get(k, k) for k in tags_to_update
                        )
                        con.print(f"  [cyan]Updated tags:[/cyan] {escape(friendly)} ({len(chapters)} chapters)")
                    return "updated"
                else:
                    logger.warning("Failed to write tags for %s", filepath)
                    return "skipped"

    # Display chapters
    if not quiet or preview:
        con.print(f"  [bold]Tracklist:[/bold] {escape(export.title)}")
        con.print(f"  [bold]Chapters:[/bold]  {len(chapters)}")
        if preview:
            for ch in chapters:
                con.print(f"    [dim]{ch.timestamp[:8]}[/dim] {escape(ch.title)}")

    if preview:
        return "skipped"

    # Embed
    success = embed_chapters(filepath, chapters, tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type, dj_artists=export.dj_artists)
    if success:
        if not quiet:
            con.print(f"  [green]Embedded {len(chapters)} chapters.[/green]")
        return "added"
    else:
        con.print("  [red]Failed to embed chapters (mkvpropedit error).[/red]")
        return "error"


def _select_interactive(results: list, duration_mins: int, query_parts=None, console: Console | None = None) -> object | None:
    """Display results table and prompt for selection."""
    con = console or make_console()

    con.print(f"\n  [bold]Search Results[/bold] [dim](video: {duration_mins}m)[/dim]")
    table = results_table(results, duration_mins, query_parts)
    con.print(table)
    con.print("   [dim]0. Cancel[/dim]\n")

    max_show = min(len(results), 15)
    while True:
        try:
            choice = input(f"  Select (1-{max_show}, or 0): ").strip()
            if not choice:
                continue
            num = int(choice)
            if num == 0:
                return None
            if 1 <= num <= max_show:
                return results[num - 1]
        except (ValueError, EOFError):
            return None


def _display_auto_selected(result, duration_mins: int, console: Console | None = None) -> None:
    """Print auto-selection info."""
    con = console or make_console()
    dur_str = f"{result.duration_mins}m" if result.duration_mins else "?"
    diff_str = ""
    if result.duration_mins and duration_mins:
        diff = result.duration_mins - duration_mins
        diff_str = f" ({diff:+d}m)" if diff != 0 else ""
    con.print(f"  [bold]Auto-selected:[/bold] {escape(result.title)} [dim]\\[{dur_str}{diff_str}] (score: {result.score:.0f})[/dim]")


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
