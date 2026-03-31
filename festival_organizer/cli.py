"""Command-line interface with workflow-oriented subcommands."""
import argparse
import sys
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.console import make_console
from festival_organizer.library import find_library_root, init_library
from festival_organizer import metadata
from festival_organizer.log import setup_logging
from festival_organizer.metadata import configure_tools
from festival_organizer.operations import (
    OrganizeOperation, NfoOperation, ArtOperation, FanartOperation,
    PosterOperation, AlbumPosterOperation, TagsOperation,
)
from festival_organizer.progress import ProgressPrinter
from festival_organizer.runner import run_pipeline
from festival_organizer.scanner import scan_folder
from festival_organizer.templates import render_folder, render_filename


HELP_TEXT = """\
CrateDigger — Festival set & concert library manager

Common workflows:
  cratedigger scan ./downloads          Preview what would happen (dry run)
  cratedigger organize ./downloads      Organize files into library structure
  cratedigger enrich ./library          Add art, posters, tags to existing files
  cratedigger chapters ./file.mkv       Add 1001Tracklists chapters
  cratedigger audit-logos ./library     Check curated festival logo coverage

Run 'cratedigger <command> --help' for details on each command.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cratedigger",
        description=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    def add_common(p):
        p.add_argument("root", type=str, help="File or folder to process")
        p.add_argument("--output", "-o", type=str, help="Output folder")
        p.add_argument("--layout", choices=[
            "artist_flat", "festival_flat", "artist_nested", "festival_nested"
        ], help="Folder layout")
        p.add_argument("--config", type=str, help="Path to config.json")
        p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")
        p.add_argument("--verbose", "-v", action="store_true", help="Show decisions and downloads")
        p.add_argument("--debug", action="store_true", help="Show all internal details")

    # scan (dry-run)
    scan_p = sub.add_parser("scan", help="Preview what would happen (dry run)")
    add_common(scan_p)

    # dry-run alias for scan
    dryrun_p = sub.add_parser("dry-run", help="Alias for scan — preview what would happen")
    add_common(dryrun_p)

    # organize
    org_p = sub.add_parser("organize", help="Move/copy files into library structure")
    add_common(org_p)
    org_p.add_argument("--move", action="store_true", help="Move instead of copy (default: copy)")
    org_p.add_argument("--rename-only", action="store_true", help="Rename in place only")
    org_p.add_argument("--enrich", action="store_true",
                       help="Also run enrichment after organizing")
    org_p.add_argument("--yes", "-y", action="store_true",
                       help="Skip confirmation prompts")

    # enrich
    enr_p = sub.add_parser("enrich", help="Add metadata artifacts to files in place")
    add_common(enr_p)
    enr_p.add_argument("--only", type=str,
                       help="Comma-separated: nfo,art,fanart,posters,tags,chapters")
    enr_p.add_argument("--force", action="store_true",
                       help="Regenerate even if artifacts exist")

    # chapters
    chap_p = sub.add_parser("chapters", help="Add 1001Tracklists chapters")
    chap_p.add_argument("root", type=str, help="File or folder to process")
    chap_p.add_argument("--tracklist", "-t", type=str, help="Tracklist URL, ID, or query")
    chap_p.add_argument("--auto", action="store_true", help="Batch mode — no prompts")
    chap_p.add_argument("--preview", action="store_true", help="Show chapters without embedding")
    chap_p.add_argument("--force", action="store_true", help="Ignore stored URLs, fresh search")
    chap_p.add_argument("--delay", type=int, help="Delay between files (seconds)")
    chap_p.add_argument("--config", type=str, help="Path to config.json")
    chap_p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")
    chap_p.add_argument("--verbose", "-v", action="store_true", help="Show decisions and downloads")
    chap_p.add_argument("--debug", action="store_true", help="Show all internal details")

    # audit-logos
    audit_p = sub.add_parser("audit-logos", help="Check curated festival logo coverage")
    audit_p.add_argument("root", type=str, help="Library folder to audit")
    audit_p.add_argument("--config", type=str, help="Path to config.json")
    audit_p.add_argument("--verbose", "-v", action="store_true")
    audit_p.add_argument("--debug", action="store_true")

    return parser


def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        return _run_command(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_command(args) -> int:
    # Resolve config layers
    config_path = Path(args.config) if getattr(args, "config", None) else None
    root = Path(args.root)

    # Find library root
    library_root = find_library_root(root) if root.exists() else None
    library_config_dir = (library_root / ".cratedigger") if library_root else None

    config = load_config(
        config_path=config_path,
        library_config_dir=library_config_dir,
    )
    configure_tools(config)

    verbose = getattr(args, "verbose", False)
    debug = getattr(args, "debug", False)
    setup_logging(verbose=verbose, debug=debug)

    console = make_console()

    # Layout override
    if getattr(args, "layout", None):
        config._data["default_layout"] = args.layout

    # dry-run is an alias for scan
    if args.command == "dry-run":
        args.command = "scan"

    # Handle chapters separately
    if args.command == "chapters":
        from festival_organizer.tracklists.cli_handler import run_chapters
        # Map new flag names to what cli_handler expects
        args.auto_select = getattr(args, "auto", False)
        args.ignore_stored_url = getattr(args, "force", False)
        return run_chapters(args, config, console=console)

    if args.command == "audit-logos":
        return _run_audit_logos(root, config, console)

    if not root.exists():
        print(f"Error: path does not exist: {root}", file=sys.stderr)
        return 1

    # Determine output root
    output = Path(args.output) if getattr(args, "output", None) else None
    explicit_output = output is not None
    if output is None:
        output = library_root if library_root else root

    # Organize safety: confirm when source is inside existing library
    if args.command == "organize" and library_root and not explicit_output:
        try:
            root.resolve().relative_to(library_root.resolve())
            is_inside_library = True
        except ValueError:
            is_inside_library = False

        if is_inside_library and not getattr(args, "yes", False):
            print(f"Re-organizing library at {library_root} "
                  f"with layout '{config.default_layout}'",
                  file=sys.stderr)
            if sys.stdin.isatty():
                try:
                    answer = input("Continue? [y/N] ").strip().lower()
                except EOFError:
                    answer = ""
                if answer not in ("y", "yes"):
                    print("Aborted.", file=sys.stderr)
                    return 0
            else:
                print("Error: re-organizing in-place requires confirmation. "
                      "Use --yes to skip.", file=sys.stderr)
                return 1

    # Initialize library marker on first organize
    if args.command == "organize" and not library_root:
        init_library(output, layout=config.default_layout)

    quiet = args.quiet

    # Scan
    progress = ProgressPrinter(total=0, console=console, quiet=quiet, verbose=verbose)
    tools = []
    if metadata.MEDIAINFO_PATH:
        tools.append("mediainfo")
    if metadata.FFPROBE_PATH:
        tools.append("ffprobe")
    if metadata.MKVEXTRACT_PATH:
        tools.append("mkvextract")
    if metadata.MKVPROPEDIT_PATH:
        tools.append("mkvpropedit")
    progress.print_header(
        command=args.command.capitalize(),
        source=root, output=output,
        layout=config.default_layout, tools=tools,
    )

    console.print("Scanning...")
    files = scan_folder(root, config)
    console.print(f"Found {len(files)} media file(s).\n")
    if not files:
        console.print("Nothing to do.")
        return 0

    progress.total = len(files)

    # Analyze + classify
    media_files = []
    for fp in files:
        mf = analyse_file(fp, root, config)
        mf.content_type = classify(mf, root, config)
        media_files.append((fp, mf))

    # Build operations per file
    force = getattr(args, "force", False)
    only = set()
    if getattr(args, "only", None):
        only = set(args.only.split(","))
    pipeline_files = []

    # Shared operation instances (deduplicate across files)
    fanart_op = None
    album_poster_op = None
    if args.command in ("enrich", "organize"):
        should_fanart = (args.command == "enrich" and (not only or "fanart" in only)) or \
                        (args.command == "organize" and getattr(args, "enrich", False))
        if should_fanart and config.fanart_enabled and config.fanart_project_api_key:
            fanart_op = FanartOperation(config, library_root=output, force=force)
        if args.command == "enrich" and (not only or "posters" in only):
            album_poster_op = AlbumPosterOperation(config, force=force, library_root=output)

    for fp, mf in media_files:
        ops: list = []

        if args.command == "scan":
            # Dry run — no operations, just show plan
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            progress.file_start(fp, target_folder + "/" + target_name)
            progress.file_done([])
            continue

        if args.command == "organize":
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            action = "move" if getattr(args, "move", False) else \
                     "rename" if getattr(args, "rename_only", False) else "copy"
            ops.append(OrganizeOperation(target=target, action=action))

            if getattr(args, "enrich", False):
                ops.append(NfoOperation(config))
                ops.append(ArtOperation())
                if fanart_op:
                    ops.append(fanart_op)
                ops.append(PosterOperation(config))
                ops.append(TagsOperation())

        elif args.command == "enrich":
            if not only or "nfo" in only:
                ops.append(NfoOperation(config, force=force))
            if not only or "art" in only:
                ops.append(ArtOperation(force=force))
            if fanart_op:
                ops.append(fanart_op)
            if not only or "posters" in only:
                ops.append(PosterOperation(config, force=force))
                if album_poster_op:
                    ops.append(album_poster_op)
            if not only or "tags" in only:
                ops.append(TagsOperation(force=force))

        pipeline_files.append((fp, mf, ops))

    if args.command == "scan":
        progress.print_summary()
        return 0

    # Run pipeline
    all_results = run_pipeline(pipeline_files, progress)

    # If enrich includes chapters, run chapters handler in auto mode
    if args.command == "enrich" and only and "chapters" in only:
        from festival_organizer.tracklists.cli_handler import run_chapters
        import types
        chap_args = types.SimpleNamespace(
            root=str(root),
            tracklist=None,
            auto_select=True,
            ignore_stored_url=force,
            preview=False,
            delay=None,
            config=getattr(args, "config", None),
            quiet=quiet,
        )
        run_chapters(chap_args, config, console=console)

    # Post-pipeline: clean up empty source directories after organize (move)
    if args.command == "organize":
        action = "move" if getattr(args, "move", False) else \
                 "rename" if getattr(args, "rename_only", False) else "copy"
        if action == "move" and root.resolve() != output.resolve():
            from festival_organizer.library import cleanup_empty_dirs
            cleanup_empty_dirs(root)

    progress.print_summary()

    # Print curated logo summary if album posters were generated
    if album_poster_op:
        summary = album_poster_op.logo_summary()
        if summary:
            console.print()
            for line in summary:
                console.print(line)

    return 0


def _run_audit_logos(root: Path, config, console) -> int:
    """Audit curated festival logo coverage for a library."""
    from festival_organizer.library import find_library_root

    library_root = find_library_root(root) if root.exists() else None
    if not library_root:
        print(f"Error: not a CrateDigger library: {root}", file=sys.stderr)
        return 1

    # Scan all media files for canonical festival names
    festivals_found: set[str] = set()
    for video in root.rglob("*"):
        if video.suffix.lower() in (".mkv", ".mp4", ".webm") and video.is_file():
            from festival_organizer.analyzer import analyse_file
            mf = analyse_file(video, video.parent, config)
            if mf.festival:
                canonical = config.resolve_festival_alias(mf.festival)
                festivals_found.add(canonical)

    # Check logo availability for each festival
    logo_dirs = [
        library_root / ".cratedigger" / "festivals",
        Path.home() / ".cratedigger" / "festivals",
    ]

    def find_logo(festival: str) -> Path | None:
        for base in logo_dirs:
            d = base / festival
            for ext in ("jpg", "jpeg", "png", "webp"):
                candidate = d / f"logo.{ext}"
                if candidate.exists():
                    return candidate
        return None

    # Report
    have_logo: list[tuple[str, Path]] = []
    missing_logo: list[str] = []
    for fest in sorted(festivals_found):
        logo = find_logo(fest)
        if logo:
            have_logo.append((fest, logo))
        else:
            missing_logo.append(fest)

    console.print(f"[bold]Library:[/bold] {library_root}")
    console.print(f"[bold]Festivals found:[/bold] {len(festivals_found)}")
    console.print()

    if have_logo:
        console.print(f"[green]With curated logo ({len(have_logo)}):[/green]")
        for fest, path in have_logo:
            console.print(f"  {fest}: [dim]{path}[/dim]")
        console.print()

    if missing_logo:
        console.print(f"[yellow]Missing curated logo ({len(missing_logo)}):[/yellow]")
        for fest in missing_logo:
            suggested = library_root / ".cratedigger" / "festivals" / fest
            console.print(f"  {fest}")
            console.print(f"    [dim]-> place logo at: {suggested}/logo.png[/dim]")
        console.print()

    # Check for unmatched folders
    for base in logo_dirs:
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir() and d.name not in festivals_found:
                    has_logo = any((d / f"logo.{ext}").exists()
                                  for ext in ("jpg", "jpeg", "png", "webp"))
                    if has_logo:
                        console.print(f"[dim]Unmatched folder (not in library): {d.name}[/dim]")

    # Warn about unsupported formats
    for base in logo_dirs:
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    for f in d.iterdir():
                        if f.suffix.lower() in (".svg", ".gif", ".bmp", ".tiff"):
                            console.print(f"[yellow]Unsupported format: {f}[/yellow]")

    return 0
