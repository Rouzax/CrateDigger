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
from festival_organizer.nfo import generate_nfo
from festival_organizer.planner import plan_actions
from festival_organizer.scanner import scan_folder


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

    # nfo (generate NFOs only)
    nfo_p = sub.add_parser("nfo", help="Generate Kodi NFO files without moving")
    add_common(nfo_p)

    # extract-art (extract cover art only)
    art_p = sub.add_parser("extract-art", help="Extract cover art without moving")
    add_common(art_p)

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

    root = Path(args.root)
    if not root.exists():
        print(f"Error: folder does not exist: {root}", file=sys.stderr)
        return 1

    # Load config
    config_path = Path(args.config) if args.config else Path("config.json")
    config = load_config(config_path if config_path.exists() else None)

    # Override layout if specified
    if getattr(args, "layout", None):
        config._data["default_layout"] = args.layout

    # Re-resolve tool paths with config overrides
    configure_tools(config)

    # Handle chapters subcommand separately (different workflow)
    if args.command == "chapters":
        from festival_organizer.tracklists.cli_handler import run_chapters
        return run_chapters(args, config)

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
    if metadata.MEDIAINFO_PATH:
        print(f"Tool:    MediaInfo ({metadata.MEDIAINFO_PATH})")
    elif metadata.FFPROBE_PATH:
        print(f"Tool:    ffprobe ({metadata.FFPROBE_PATH})")
    else:
        print(f"Tool:    NONE (filename parsing only)")
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

    # Handle nfo/extract-art subcommands
    if args.command == "nfo":
        return _run_nfo_only(media_files, output, config, verbose)
    if args.command == "extract-art":
        return _run_extract_art_only(media_files, output, config, verbose)

    # Plan
    actions = plan_actions(
        media_files, output, config,
        action=action_type,
        layout_name=args.layout,
        generate_nfo=gen_nfo,
        extract_art=ext_art,
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

            # Post-move tasks
            if a.status == "done":
                if a.generate_nfo:
                    generate_nfo(a.media_file, a.target, config)
                if a.extract_art and a.media_file.has_cover:
                    extract_cover(a.source, a.target.parent)

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
        if mf.has_cover:
            result = extract_cover(mf.source_path, mf.source_path.parent)
            if result and verbose:
                print(f"  [ART] {result}")
                count += 1
    print(f"\nExtracted {count} cover art file(s).")
    return 0
