"""Command-line interface with subcommands."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.artwork import extract_cover
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.executor import execute_actions
from festival_organizer.logging_util import ActionLogger
from festival_organizer import metadata
from festival_organizer.metadata import configure_tools
from festival_organizer.models import FileAction
from festival_organizer.embed_tags import embed_tags as embed_tags_fn
from festival_organizer.nfo import generate_nfo
from festival_organizer.planner import plan_actions
from festival_organizer.poster import generate_set_poster
from festival_organizer.scanner import scan_folder


def _run_post_processing(action: FileAction, config) -> None:
    """Run post-processing steps for a completed or skipped action.

    For 'done' actions the file is at action.target.
    For 'skipped' actions the file is at action.source (it never moved).
    """
    if action.status not in ("done", "skipped"):
        return

    file_path = action.target if action.status == "done" else action.source
    mf = action.media_file

    # 1. NFO
    if action.generate_nfo:
        generate_nfo(mf, file_path, config)

    # 2. Thumb (no has_cover gate — frame_sampler handles fallback)
    thumb_path = None
    if action.extract_art:
        thumb_path = extract_cover(file_path, file_path.parent)

    # 3. Set poster (needs thumb as source image)
    if action.generate_posters and thumb_path:
        poster_path = file_path.with_name(f"{file_path.stem}-poster.jpg")
        festival_display = config.get_festival_display(mf.festival, mf.location) if mf.location else mf.festival
        generate_set_poster(
            source_image_path=thumb_path,
            output_path=poster_path,
            artist=mf.artist or "Unknown",
            festival=festival_display or mf.title or "",
            date=mf.date,
            year=mf.year,
            detail=mf.stage or mf.location or "",
        )

    # 4. Embed tags
    if action.embed_tags:
        embed_tags_fn(mf, file_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organize",
        description="Festival Set Organizer — scan, rename, and sort media files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    def add_common(p):
        p.add_argument("root", type=str, help="Root folder to scan")
        p.add_argument("--output", "-o", type=str, help="Output folder (default: same as root)")
        p.add_argument("--layout", choices=["artist_first", "festival_first"], help="Folder layout")
        p.add_argument("--config", type=str, help="Path to config.json")
        p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")

    # scan (dry-run)
    scan_p = sub.add_parser("scan", help="Dry-run: show what would be changed")
    add_common(scan_p)

    # execute
    exec_p = sub.add_parser("execute", help="Move/rename files")
    add_common(exec_p)
    exec_p.add_argument("--copy", action="store_true", help="Copy instead of move")
    exec_p.add_argument("--rename-only", action="store_true", help="Rename in place only")
    exec_p.add_argument("--generate-nfo", action="store_true", help="Generate Kodi NFO files")
    exec_p.add_argument("--extract-art", action="store_true", help="Extract cover art from MKV")
    exec_p.add_argument("--generate-posters", action="store_true", help="Generate set poster images")
    exec_p.add_argument("--embed-tags", action="store_true", help="Embed Plex tags via mkvpropedit")

    # nfo (generate NFOs only)
    nfo_p = sub.add_parser("nfo", help="Generate Kodi NFO files without moving")
    add_common(nfo_p)

    # extract-art (extract cover art only)
    art_p = sub.add_parser("extract-art", help="Extract cover art without moving")
    add_common(art_p)

    # posters (generate set posters only)
    poster_p = sub.add_parser("posters", help="Generate set posters without moving")
    add_common(poster_p)

    # chapters
    chap_p = sub.add_parser("chapters", help="Add tracklist chapters to MKV files")
    chap_p.add_argument("root", type=str, help="File or folder to process")
    chap_p.add_argument("--tracklist", "-t", type=str, help="Tracklist URL, ID, or search query")
    chap_p.add_argument("--auto-select", action="store_true", help="Auto-select best match")
    chap_p.add_argument("--ignore-stored-url", action="store_true", help="Force fresh search")
    chap_p.add_argument("--preview", action="store_true", help="Show chapters without embedding")
    chap_p.add_argument("--delay", type=int, help="Delay between files in seconds")
    chap_p.add_argument("--config", type=str, help="Path to config.json")
    chap_p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")

    return parser


def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Load config
    config_path = Path(getattr(args, "config", None) or "config.json")
    config = load_config(config_path if config_path.exists() else None)

    # Re-resolve tool paths with config overrides
    configure_tools(config)

    # Handle chapters subcommand separately (different workflow)
    if args.command == "chapters":
        from festival_organizer.tracklists.cli_handler import run_chapters
        return run_chapters(args, config)

    root = Path(args.root)
    if not root.exists():
        print(f"Error: folder does not exist: {root}", file=sys.stderr)
        return 1

    # Override layout if specified
    if getattr(args, "layout", None):
        config._data["default_layout"] = args.layout

    output = Path(args.output) if args.output else root
    verbose = not args.quiet

    # Header
    dry_run = args.command == "scan"
    mode = "DRY-RUN" if dry_run else args.command.upper()
    print(f"Festival Set Organizer")
    print(f"{'=' * 60}")
    print(f"Source:  {root}")
    print(f"Output:  {output}")
    print(f"Mode:    {mode}")
    print(f"Layout:  {config.default_layout}")
    tools = []
    if metadata.MEDIAINFO_PATH:
        tools.append(f"MediaInfo ({metadata.MEDIAINFO_PATH})")
    if metadata.FFPROBE_PATH:
        tools.append(f"ffprobe ({metadata.FFPROBE_PATH})")
    if metadata.MKVEXTRACT_PATH:
        tools.append(f"mkvextract ({metadata.MKVEXTRACT_PATH})")
    if metadata.MKVPROPEDIT_PATH:
        tools.append(f"mkvpropedit ({metadata.MKVPROPEDIT_PATH})")
    if tools:
        print(f"Tools:   {tools[0]}")
        for t in tools[1:]:
            print(f"         {t}")
    else:
        print(f"Tools:   NONE (filename parsing only)")
    print(f"{'=' * 60}\n")

    # Scan
    print("Scanning...")
    files = scan_folder(root, config)
    print(f"Found {len(files)} media file(s).\n")
    if not files:
        print("Nothing to do.")
        return 0

    # Analyse + classify
    media_files = []
    for fp in files:
        mf = analyse_file(fp, root, config)
        mf.content_type = classify(mf, root, config)
        media_files.append(mf)

    # Determine action type
    action_type = "move"
    if hasattr(args, "copy") and args.copy:
        action_type = "copy"
    elif hasattr(args, "rename_only") and args.rename_only:
        action_type = "rename"

    gen_nfo = hasattr(args, "generate_nfo") and args.generate_nfo
    ext_art = hasattr(args, "extract_art") and args.extract_art
    gen_posters = hasattr(args, "generate_posters") and args.generate_posters
    emb_tags = hasattr(args, "embed_tags") and args.embed_tags

    # Handle nfo/extract-art subcommands
    if args.command == "nfo":
        return _run_nfo_only(media_files, output, config, verbose)
    if args.command == "extract-art":
        return _run_extract_art_only(media_files, output, config, verbose)
    if args.command == "posters":
        return _run_posters_only(media_files, output, config, verbose)

    # Plan
    actions = plan_actions(
        media_files, output, config,
        action=action_type,
        layout_name=args.layout,
        generate_nfo=gen_nfo,
        extract_art=ext_art,
        generate_posters=gen_posters,
        embed_tags=emb_tags,
    )

    # Log
    logger = ActionLogger(verbose=verbose)

    if dry_run:
        for a in actions:
            a.status = "pending"
            logger.log_action(a)
    else:
        # Execute
        execute_actions(actions)
        for a in actions:
            logger.log_action(a)
            _run_post_processing(a, config)

    # Save log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = output if not dry_run else Path(".")
    log_path = log_dir / f"organizer_log_{timestamp}.csv"
    try:
        logger.save_csv(log_path)
    except PermissionError:
        # Fall back to current directory
        log_path = Path(f"organizer_log_{timestamp}.csv")
        logger.save_csv(log_path)

    # Summary
    stats = logger.stats
    print(f"\n{'=' * 60}")
    print("Summary:")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")
    print(f"Log: {log_path}")
    print(f"{'=' * 60}")

    return 0


def _run_nfo_only(media_files, output, config, verbose):
    """Generate NFO files for all files without moving them."""
    count = 0
    for mf in media_files:
        nfo_path = generate_nfo(mf, mf.source_path, config)
        if verbose:
            print(f"  [NFO] {nfo_path}")
        count += 1
    print(f"\nGenerated {count} NFO file(s).")
    return 0


def _run_extract_art_only(media_files, output, config, verbose):
    """Extract cover art from all files without moving them."""
    count = 0
    for mf in media_files:
        result = extract_cover(mf.source_path, mf.source_path.parent)
        if result:
            if verbose:
                print(f"  [ART] {result}")
            count += 1
    print(f"\nExtracted {count} cover art file(s).")
    return 0


def _run_posters_only(media_files, output, config, verbose):
    """Generate set posters for all files without moving them."""
    count = 0
    for mf in media_files:
        # Need thumb first
        thumb_path = extract_cover(mf.source_path, mf.source_path.parent)
        if not thumb_path:
            if verbose:
                print(f"  [SKIP] {mf.source_path.name} — no thumb available")
            continue

        poster_path = mf.source_path.with_name(f"{mf.source_path.stem}-poster.jpg")
        festival_display = config.get_festival_display(mf.festival, mf.location) if mf.location else mf.festival
        generate_set_poster(
            source_image_path=thumb_path,
            output_path=poster_path,
            artist=mf.artist or "Unknown",
            festival=festival_display or mf.title or "",
            date=mf.date,
            year=mf.year,
            detail=mf.stage or mf.location or "",
        )
        if verbose:
            print(f"  [POSTER] {poster_path}")
        count += 1
    print(f"\nGenerated {count} poster(s).")
    return 0
