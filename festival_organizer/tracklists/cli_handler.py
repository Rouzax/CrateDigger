"""CLI handler for the 'chapters' subcommand."""
import sys
import time
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import Config
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


def run_chapters(args, config: Config) -> int:
    """Main entry point for the 'chapters' subcommand."""
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
    source_cache = SourceCache()
    session = TracklistSession(source_cache=source_cache, delay=delay)
    email, password = _get_credentials(config)
    if not email or not password:
        print("Error: credentials required. Set TRACKLISTS_EMAIL and TRACKLISTS_PASSWORD environment variables.", file=sys.stderr)
        return 1

    try:
        session.login(email, password)
    except AuthenticationError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1

    print(f"Tracklist Chapters")
    print(f"{'=' * 60}")
    print(f"Source:  {root}")
    print(f"Files:   {len(files)}")
    print(f"Mode:    {'preview' if preview else 'embed'}")
    print(f"Select:  {'auto' if auto_select else 'interactive'}")
    print(f"{'=' * 60}\n")

    # Process files
    stats = {"added": 0, "up_to_date": 0, "skipped": 0, "error": 0}

    for i, filepath in enumerate(files):
        if i > 0 and not preview:
            time.sleep(delay)

        if not quiet:
            print(f"\n[{i+1}/{len(files)}] {filepath.name}")

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
            )
            stats[status] = stats.get(status, 0) + 1
        except KeyboardInterrupt:
            print("\nAborted by user.")
            break
        except Exception as e:
            print(f"  Error: {e}")
            stats["error"] += 1

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    for status, count in sorted(stats.items()):
        if count > 0:
            print(f"  {status}: {count}")
    print(f"{'=' * 60}")

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
) -> str:
    """Process a single file. Returns status string."""
    # Analyse file for metadata
    mf = analyse_file(filepath, scan_root, config)
    mf.content_type = classify(mf, scan_root, config)
    duration_mins = int(mf.duration_seconds / 60) if mf.duration_seconds else 0

    # Check for stored tracklist URL
    if not ignore_stored:
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            if auto_select:
                print(f"  Using stored URL: {stored['url']}")
                return _fetch_and_embed(
                    session, stored["url"], filepath, duration_mins,
                    config, preview, quiet, language,
                )
            else:
                choice = input(f"  Stored URL: {stored['url']}\n  Use stored? (Y)es / (S)kip / (R)esearch: ").strip().lower()
                if choice in ("y", "yes", ""):
                    return _fetch_and_embed(
                        session, stored["url"], filepath, duration_mins,
                        config, preview, quiet, language,
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
            config, preview, quiet, language,
        )
    elif source["type"] == "id":
        return _fetch_and_embed(
            session, None, filepath, duration_mins,
            config, preview, quiet, language,
            tracklist_id=source["value"],
        )

    # Search
    query_str = source["value"]

    # Expand known abbreviations for better API results (AMF → Amsterdam Music Festival)
    aliases = {**source_cache.derive_aliases(), **config.tracklists_aliases}
    query_str = expand_aliases_in_query(query_str, aliases)

    if not quiet:
        print(f"  Searching: {query_str}")

    results = session.search(query_str, duration_minutes=duration_mins, year=mf.year or None)

    if not results:
        print("  No results found.")
        return "skipped"

    # Score results (aliases already loaded above)
    query_parts = parse_query(query_str, aliases)
    scored = score_results(results, query_parts, duration_mins)

    if not scored:
        print("  No relevant results after filtering.")
        return "skipped"

    # Select result
    if auto_select:
        selected = scored[0]
        if not quiet:
            _display_auto_selected(selected, duration_mins)
    else:
        selected = _select_interactive(scored, duration_mins)
        if selected is None:
            return "skipped"

    # Fetch and embed
    tl_id = selected.id
    return _fetch_and_embed(
        session, selected.url, filepath, duration_mins,
        config, preview, quiet, language,
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
) -> str:
    """Fetch tracklist, parse chapters, and embed."""
    if not tracklist_id and url:
        tracklist_id = extract_tracklist_id(url)

    export = session.export_tracklist(tracklist_id, full_url=url)

    try:
        chapters = parse_tracklist_lines(export.lines, language=language)
    except ValueError as e:
        print(f"  {e}")
        if not preview:
            # Tag file with URL for future pickup
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type)
            print(f"  Tagged with URL for future pickup.")
        return "skipped"

    if not chapters:
        print("  No chapters found in tracklist.")
        return "skipped"

    if len(chapters) < 2:
        print("  Only 1 chapter — skipping (not useful for navigation)")
        if not preview:
            embed_chapters(filepath, [], tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type)
            print(f"  Tagged with URL for future pickup.")
        return "skipped"

    # Check for duplicates
    existing = extract_existing_chapters(filepath)
    if chapters_are_identical(existing, chapters):
        stored = extract_stored_tracklist_info(filepath)
        if stored and stored.get("url"):
            # Chapters match — check if tags need updating
            desired = {
                "CRATEDIGGER_1001TL_URL": export.url,
                "CRATEDIGGER_1001TL_TITLE": export.title,
                "CRATEDIGGER_1001TL_ID": tracklist_id or "",
                "CRATEDIGGER_1001TL_DATE": tracklist_date or "",
                "CRATEDIGGER_1001TL_GENRES": "|".join(export.genres) if export.genres else "",
                "CRATEDIGGER_1001TL_DJ_ARTWORK": export.dj_artwork_url,
            }
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
            }
            # Only update tags that have a new non-empty value different from stored
            tags_to_update = {
                k: v for k, v in desired.items()
                if v and v != stored_map.get(k, "")
            }
            if not tags_to_update:
                if not quiet:
                    print(f"  Up to date ({len(chapters)} chapters)")
                return "up_to_date"
            # Re-embed only the changed tags, skip chapter writing
            if not preview:
                write_merged_tags(filepath, {70: tags_to_update})
                if not quiet:
                    print(f"  Updated tags: {', '.join(tags_to_update.keys())}")
                return "added"

    # Display chapters
    if not quiet or preview:
        print(f"  Tracklist: {export.title}")
        print(f"  Chapters:  {len(chapters)}")
        if preview:
            for ch in chapters:
                print(f"    [{ch.timestamp[:8]}] {ch.title}")

    if preview:
        return "skipped"

    # Embed
    success = embed_chapters(filepath, chapters, tracklist_url=export.url, tracklist_title=export.title, tracklist_id=tracklist_id, tracklist_date=tracklist_date, genres=export.genres, dj_artwork_url=export.dj_artwork_url, stage_text=export.stage_text, sources_by_type=export.sources_by_type)
    if success:
        if not quiet:
            print(f"  Embedded {len(chapters)} chapters.")
        return "added"
    else:
        print("  Failed to embed chapters (mkvpropedit error).")
        return "error"


def _select_interactive(results: list, duration_mins: int) -> object | None:
    """Display numbered list and prompt for selection."""
    max_show = 15
    shown = results[:max_show]

    print(f"\n  Search Results (video: {duration_mins}m):")
    print(f"  {'-' * 50}")

    for i, r in enumerate(shown, 1):
        # Quality indicator
        if r.score >= 250:
            indicator = "+"
        elif r.score >= 150:
            indicator = "~"
        elif r.score >= 80:
            indicator = "?"
        else:
            indicator = "-"

        dur_str = f"{r.duration_mins}m" if r.duration_mins else "?"
        diff_str = ""
        if r.duration_mins and duration_mins:
            diff = r.duration_mins - duration_mins
            diff_str = f" ({diff:+d}m)" if diff != 0 else " (=)"

        date_str = r.date or ""
        print(f"  {i:>2}. [{indicator}] {r.title} [{date_str} | {dur_str}{diff_str}]")

    print(f"  {'-' * 50}")
    print(f"   0. Cancel\n")

    while True:
        try:
            choice = input(f"  Select (1-{len(shown)}, or 0): ").strip()
            if not choice:
                continue
            num = int(choice)
            if num == 0:
                return None
            if 1 <= num <= len(shown):
                return shown[num - 1]
        except (ValueError, EOFError):
            return None


def _display_auto_selected(result, duration_mins: int) -> None:
    """Print auto-selection info."""
    dur_str = f"{result.duration_mins}m" if result.duration_mins else "?"
    diff_str = ""
    if result.duration_mins and duration_mins:
        diff = result.duration_mins - duration_mins
        diff_str = f" ({diff:+d}m)" if diff != 0 else ""
    print(f"  Auto-selected: {result.title} [{dur_str}{diff_str}] (score: {result.score:.0f})")


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
