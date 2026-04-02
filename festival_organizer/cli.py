"""Command-line interface with workflow-oriented subcommands."""
import sys
import types
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Optional

import typer

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.console import escape, make_console
from festival_organizer.library import init_library, resolve_library_root
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


# ---------------------------------------------------------------------------
# Shared type aliases (single source of truth for help text)
# ---------------------------------------------------------------------------

RootArg = Annotated[str, typer.Argument(help="File or folder to process")]
OutputOpt = Annotated[Optional[str], typer.Option("--output", "-o", help="Output folder")]
ConfigOpt = Annotated[Optional[str], typer.Option("--config", help="Path to config.json")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress per-file output")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Show decisions and downloads")]
DebugOpt = Annotated[bool, typer.Option("--debug", help="Show all internal details")]


class Layout(StrEnum):
    artist_flat = "artist_flat"
    festival_flat = "festival_flat"
    artist_nested = "artist_nested"
    festival_nested = "festival_nested"


LayoutOpt = Annotated[Optional[Layout], typer.Option("--layout", help="Folder layout")]


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="cratedigger",
    help="CrateDigger: Festival set & concert library manager",
    rich_markup_mode="rich",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """CrateDigger: Festival set & concert library manager."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Helper: build namespace from command params and delegate to _run_command
# ---------------------------------------------------------------------------

def _dispatch(command: str, params: dict) -> int:
    params = {k: v for k, v in params.items() if k != "command"}
    ns = types.SimpleNamespace(command=command, **params)
    if hasattr(ns, "layout") and ns.layout is not None:
        ns.layout = ns.layout.value
    return _run_command(ns)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def scan(
    root: RootArg,
    output: OutputOpt = None,
    layout: LayoutOpt = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Preview what would happen (dry run)."""
    return _dispatch("scan", locals())


@app.command(name="dry-run")
def dry_run(
    root: RootArg,
    output: OutputOpt = None,
    layout: LayoutOpt = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Alias for scan; preview what would happen."""
    return _dispatch("dry-run", locals())


@app.command()
def organize(
    root: RootArg,
    output: OutputOpt = None,
    layout: LayoutOpt = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    move: Annotated[bool, typer.Option("--move", help="Move instead of copy (default: copy)")] = False,
    rename_only: Annotated[bool, typer.Option("--rename-only", help="Rename in place only")] = False,
    enrich: Annotated[bool, typer.Option("--enrich", help="Also run enrichment after organizing")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Move/copy files into library structure."""
    return _dispatch("organize", locals())


@app.command()
def enrich(
    root: RootArg,
    output: OutputOpt = None,
    layout: LayoutOpt = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    only: Annotated[Optional[str], typer.Option("--only", help="Comma-separated: nfo,art,fanart,posters,tags,chapters")] = None,
    force: Annotated[bool, typer.Option("--force", help="Regenerate even if artifacts exist")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Add metadata artifacts to files in place."""
    return _dispatch("enrich", locals())


@app.command()
def chapters(
    root: RootArg,
    tracklist: Annotated[Optional[str], typer.Option("--tracklist", "-t", help="Tracklist URL, ID, or query")] = None,
    auto: Annotated[bool, typer.Option("--auto", help="Batch mode, no prompts")] = False,
    preview: Annotated[bool, typer.Option("--preview", help="Show chapters without embedding")] = False,
    force: Annotated[bool, typer.Option("--force", help="Ignore stored URLs, fresh search")] = False,
    delay: Annotated[Optional[int], typer.Option("--delay", help="Delay between files (seconds)")] = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Add 1001Tracklists chapters."""
    return _dispatch("chapters", locals())


@app.command(name="audit-logos")
def audit_logos(
    root: Annotated[str, typer.Argument(help="Library folder to audit")],
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Check curated festival logo coverage."""
    return _dispatch("audit-logos", locals())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    try:
        result = app(args=argv, standalone_mode=False)
        return result if isinstance(result, int) else 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Command logic (unchanged)
# ---------------------------------------------------------------------------

def _run_command(args) -> int:
    # Resolve config layers
    config_path = Path(args.config) if getattr(args, "config", None) else None
    root = Path(args.root)

    # Determine output early so we can search it for .cratedigger
    explicit_output = getattr(args, "output", None) is not None
    output_arg = Path(args.output) if explicit_output else None

    # Find library root: check output first (if given), fall back to source
    library_root = resolve_library_root(source=root, output=output_arg)
    library_config_dir = (library_root / ".cratedigger") if library_root else None

    config = load_config(
        config_path=config_path,
        library_config_dir=library_config_dir,
    )
    configure_tools(config)

    verbose = getattr(args, "verbose", False)
    debug = getattr(args, "debug", False)
    console = make_console()
    setup_logging(verbose=verbose, debug=debug, console=console)

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
    output = output_arg
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

    if not quiet:
        with console.status("Scanning files..."):
            files = scan_folder(root, config)
        console.print(f"Found {len(files)} media files.\n")
    else:
        files = scan_folder(root, config)

    if not files:
        console.print("Nothing to do.")
        return 0

    progress.total = len(files)

    # Analyze + classify
    media_files = []
    if not quiet:
        with console.status("") as status:
            for i, fp in enumerate(files):
                status.update(f"Analyzing \\[{i+1}/{len(files)}] {escape(fp.name)}")
                mf = analyse_file(fp, root, config)
                mf.content_type = classify(mf, root, config)
                media_files.append((fp, mf))
    else:
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
            # Dry run: no operations, just show plan
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
        console.print(f"\n[dim]Dry run complete. {len(media_files)} files scanned.[/dim]")
        return 0

    # Run pipeline
    all_results = run_pipeline(pipeline_files, progress)

    # If enrich includes chapters, run chapters handler in auto mode
    if args.command == "enrich" and only and "chapters" in only:
        from festival_organizer.tracklists.cli_handler import run_chapters
        import types as _types
        chap_args = _types.SimpleNamespace(
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

    # Post-pipeline: Kodi sync
    kodi_sync = getattr(args, "kodi_sync", False) or config.kodi_enabled
    if kodi_sync and args.command in ("enrich", "organize"):
        _run_kodi_sync(all_results, pipeline_files, config, console, quiet)

    return 0


def _run_kodi_sync(all_results, pipeline_files, config, console, quiet):
    """Notify Kodi to refresh items that had NFO/art/poster changes."""
    from festival_organizer.kodi import KodiClient, sync_library

    RELEVANT_OPS = {"nfo", "art", "poster", "album_poster"}
    changed_paths: list[Path] = []

    for (fp, _mf, ops), results in zip(pipeline_files, all_results):
        final_path = fp
        for op, result in zip(ops, results):
            if op.name == "organize" and result.status == "done":
                final_path = op.target

        has_change = any(
            r.status == "done" and r.name in RELEVANT_OPS
            for r in results
        )
        if has_change:
            changed_paths.append(final_path)

    if not changed_paths:
        return

    try:
        client = KodiClient(
            host=config.kodi_host,
            port=config.kodi_port,
            username=config.kodi_username,
            password=config.kodi_password,
        )
        path_mapping = config.kodi_settings.get("path_mapping")
        sync_library(client, changed_paths, console, quiet,
                     path_mapping=path_mapping)
    except Exception as e:
        import logging
        logging.getLogger("festival_organizer.kodi").warning(
            "Kodi sync failed: %s", e
        )
        if not quiet:
            console.print(f"[yellow]Kodi sync failed: {e}[/yellow]")


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
                display = config.get_festival_display(mf.festival, mf.edition)
                festivals_found.add(display)

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

    console.print(f"[bold]Library:[/bold] {escape(str(library_root))}")
    console.print(f"[bold]Festivals found:[/bold] {len(festivals_found)}")
    console.print()

    if have_logo:
        console.print(f"[green]With curated logo ({len(have_logo)}):[/green]")
        for fest, path in have_logo:
            console.print(f"  {escape(fest)}: [dim]{escape(str(path))}[/dim]")
        console.print()

    if missing_logo:
        user_festivals = Path.home() / ".cratedigger" / "festivals"
        console.print(f"[yellow]Missing curated logo ({len(missing_logo)}):[/yellow]")
        for fest in missing_logo:
            lib_path = library_root / ".cratedigger" / "festivals" / fest
            usr_path = user_festivals / fest
            console.print(f"  {escape(fest)}")
            console.print(f"    [dim]-> place logo at: {escape(str(lib_path))}/logo.png[/dim]")
            console.print(f"    [dim]   or user-level: {escape(str(usr_path))}/logo.png[/dim]")
        console.print()

    # Check for unmatched folders
    for base in logo_dirs:
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir() and d.name not in festivals_found:
                    has_logo = any((d / f"logo.{ext}").exists()
                                  for ext in ("jpg", "jpeg", "png", "webp"))
                    if has_logo:
                        console.print(f"[dim]Unmatched folder (not in library): {escape(d.name)}[/dim]")

    # Warn about unsupported formats
    for base in logo_dirs:
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    for f in d.iterdir():
                        if f.suffix.lower() in (".svg", ".gif", ".bmp", ".tiff"):
                            console.print(f"[yellow]Unsupported format: {escape(str(f))}[/yellow]")

    return 0
