"""Command-line interface with workflow-oriented subcommands."""
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Optional

import typer

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.console import escape, make_console, print_error
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
LibraryArg = Annotated[str, typer.Argument(help="Library folder to process")]
OutputOpt = Annotated[Optional[str], typer.Option("--output", "-o", help="Output folder")]
ConfigOpt = Annotated[Optional[str], typer.Option("--config", help="Path to config.json")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress per-file progress")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Show detailed progress and decisions")]
DebugOpt = Annotated[bool, typer.Option("--debug", help="Show cache hits, retries, and internal mechanics")]


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
    help="CrateDigger: Festival set & concert library manager\n\nWorkflow: identify -> organize -> enrich",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
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
# Commands (in recommended workflow order)
# ---------------------------------------------------------------------------

@app.command()
def identify(
    root: RootArg,
    tracklist: Annotated[Optional[str], typer.Option("--tracklist", "-t", help="Tracklist URL, ID, or query")] = None,
    auto: Annotated[bool, typer.Option("--auto", help="Batch mode, no prompts")] = False,
    preview: Annotated[bool, typer.Option("--preview", help="Show chapters without embedding")] = False,
    regenerate: Annotated[bool, typer.Option("--regenerate", "--fresh", help="Redo even if already done", show_default=False)] = False,
    delay: Annotated[Optional[int], typer.Option("--delay", help="Delay between files, seconds (default: 5)")] = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Match files on 1001Tracklists; embed metadata and chapters."""
    return _dispatch("identify", locals())


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
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview what would happen without making changes")] = False,
    enrich: Annotated[bool, typer.Option("--enrich", help="Run all enrichment after organizing (use enrich command for selective operations)")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Move/copy files into library structure."""
    if dry_run and move:
        print("Error: --dry-run and --move cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    if dry_run and rename_only:
        print("Error: --dry-run and --rename-only cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    if move and rename_only:
        print("Error: --move and --rename-only cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    return _dispatch("organize", locals())


@app.command()
def enrich(
    root: LibraryArg,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    only: Annotated[Optional[str], typer.Option("--only", help="Comma-separated operations to run (nfo, art, fanart, posters, tags)")] = None,
    regenerate: Annotated[bool, typer.Option("--regenerate", help="Regenerate even if artifacts exist")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Add artwork, posters, NFO, and tags."""
    return _dispatch("enrich", locals())


@app.command(name="audit-logos")
def audit_logos(
    root: LibraryArg,
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Check curated festival logo coverage."""
    return _dispatch("audit-logos", locals())


# ---------------------------------------------------------------------------
# Console state helpers (Windows console mode corruption prevention)
# ---------------------------------------------------------------------------

_SAVED_CONSOLE_MODE: int | None = None


def _save_win32_console_mode() -> None:
    """Snapshot the console output mode before Rich touches it."""
    global _SAVED_CONSOLE_MODE
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            _SAVED_CONSOLE_MODE = mode.value
    except Exception:
        pass


def _restore_win32_console_mode() -> None:
    """Restore the original console output mode."""
    if _SAVED_CONSOLE_MODE is None:
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        kernel32.SetConsoleMode(handle, _SAVED_CONSOLE_MODE)
    except Exception:
        pass


def _cleanup_console() -> None:
    """Reset terminal state to prevent cross-process console corruption on Windows."""
    try:
        sys.stdout.write("\033[?25h")  # Show cursor (Rich Status/Live may hide it)
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    if sys.platform == "win32":
        _restore_win32_console_mode()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    if sys.platform == "win32":
        _save_win32_console_mode()
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
    finally:
        _cleanup_console()


def _analyse_parallel(
    files: list[Path],
    root: Path,
    config,
    max_workers: int = 4,
) -> list[tuple]:
    """Analyse and classify files using a thread pool.

    Returns list of (Path, MediaFile) tuples in the same order as input.
    Spawns mediainfo/ffprobe subprocesses in parallel to overlap I/O.
    """
    if not files:
        return []

    # Populate config._ext_cache (file I/O cache) so worker threads
    # only perform dict reads, avoiding redundant file loads.
    _ = config.known_festivals
    _ = config.artist_aliases
    _ = config.festival_aliases

    results: list[tuple | None] = [None] * len(files)

    def _worker(idx: int, fp: Path):
        mf = analyse_file(fp, root, config)
        mf.content_type = classify(mf, root, config)
        return idx, fp, mf

    with ThreadPoolExecutor(max_workers=min(len(files), max_workers)) as pool:
        futures = [pool.submit(_worker, i, fp) for i, fp in enumerate(files)]
        for future in as_completed(futures):
            idx, fp, mf = future.result()
            results[idx] = (fp, mf)

    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Command logic (unchanged)
# ---------------------------------------------------------------------------

def _run_command(args) -> int:
    start_time = time.monotonic()
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

    # Handle identify separately
    if args.command == "identify":
        from festival_organizer.tracklists.cli_handler import run_identify
        # Map new flag names to what cli_handler expects
        args.auto_select = getattr(args, "auto", False)
        args.ignore_stored_url = getattr(args, "regenerate", False)
        return run_identify(args, config, console=console)

    if args.command == "audit-logos":
        return _run_audit_logos(root, config, console,
                                verbose=verbose, debug=debug)

    if not root.exists():
        print_error(f"path does not exist: {root}", console)
        return 1

    if args.command == "enrich" and not library_root:
        print_error("not a CrateDigger library. Run organize first.", console)
        return 1

    # Determine output root
    output = output_arg
    if output is None:
        output = library_root if library_root else root

    # Organize safety: confirm when source is inside existing library
    if args.command == "organize" and not getattr(args, "dry_run", False) and library_root and not explicit_output:
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
                print_error("re-organizing in-place requires confirmation. "
                           "Use --yes to skip.", console)
                return 1

    # Initialize library marker on first organize
    if args.command == "organize" and not getattr(args, "dry_run", False) and not library_root:
        init_library(output, layout=config.default_layout)

    quiet = args.quiet

    # Scan
    progress = ProgressPrinter(total=0, console=console, quiet=quiet, verbose=verbose)
    all_tools = {
        "mediainfo": metadata.MEDIAINFO_PATH,
        "ffprobe": metadata.FFPROBE_PATH,
        "mkvextract": metadata.MKVEXTRACT_PATH,
        "mkvpropedit": metadata.MKVPROPEDIT_PATH,
    }
    missing_tools = [name for name, path in all_tools.items() if not path]

    if not quiet:
        with console.status("Scanning files..."):
            files = scan_folder(root, config)
    else:
        files = scan_folder(root, config)

    # Build command-specific header rows
    if args.command == "enrich":
        command_label = "Enrich"
        header_rows = {}
        if root.resolve() != output.resolve():
            header_rows["Path"] = str(root)
        header_rows["Library"] = str(output)
        header_rows["Files"] = str(len(files))
        if getattr(args, "only", None):
            header_rows["Operations"] = args.only
        if getattr(args, "regenerate", False):
            header_rows["Regenerate"] = "yes"
    else:
        action = "move" if getattr(args, "move", False) else \
                 "rename" if getattr(args, "rename_only", False) else "copy"
        dry_run = getattr(args, "dry_run", False)
        command_label = f"Organize (dry run, {action})" if dry_run else "Organize"
        header_rows = {
            "Source": str(root),
            "Output": str(output),
            "Layout": config.default_layout,
            "Action": action,
            "Files": str(len(files)),
        }
        if getattr(args, "enrich", False):
            header_rows["Enrich"] = "yes"
    progress.print_header(command=command_label, rows=header_rows, missing_tools=missing_tools)

    if not files:
        console.print("Nothing to do.")
        return 0

    progress.total = len(files)

    # Analyze + classify
    media_files = []
    if not quiet and not verbose and not debug:
        with console.status("") as status:
            for i, fp in enumerate(files):
                status.update(f"Analyzing [{i+1}/{len(files)}] {escape(fp.name)}")
                mf = analyse_file(fp, root, config)
                mf.content_type = classify(mf, root, config)
                media_files.append((fp, mf))
    else:
        if not quiet and (verbose or debug):
            console.print(f"Analyzing {len(files)} files...")
        for fp in files:
            mf = analyse_file(fp, root, config)
            mf.content_type = classify(mf, root, config)
            media_files.append((fp, mf))

    # Build operations per file
    force = getattr(args, "regenerate", False)
    only = set()
    if getattr(args, "only", None):
        only = {v.strip() for v in args.only.split(",")}
        valid_ops = {"nfo", "art", "fanart", "posters", "tags"}
        unknown = only - valid_ops
        if unknown:
            print_error(f"unknown operation {', '.join(repr(u) for u in sorted(unknown))}. "
                       f"Valid: {', '.join(sorted(valid_ops))}", console)
            return 1
    pipeline_files = []

    # Shared operation instances (deduplicate across files)
    fanart_op = None
    album_poster_op = None
    if args.command in ("enrich", "organize"):
        should_fanart = (args.command == "enrich" and (not only or "fanart" in only)) or \
                        (args.command == "organize" and getattr(args, "enrich", False))
        if should_fanart and config.fanart_enabled and config.fanart_project_api_key:
            images_ttl = config.cache_ttl.get("images_days", 90)
            fanart_op = FanartOperation(config, library_root=output, force=force,
                                        ttl_days=images_ttl)
        if args.command == "enrich" and (not only or "posters" in only):
            images_ttl = config.cache_ttl.get("images_days", 90)
            album_poster_op = AlbumPosterOperation(config, force=force, library_root=output,
                                                    ttl_days=images_ttl)

    for fp, mf in media_files:
        ops: list = []

        if getattr(args, "dry_run", False):
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

    if getattr(args, "dry_run", False):
        from festival_organizer.console import classification_summary_panel
        festival_count = sum(1 for _, mf in media_files if mf.content_type == "festival_set")
        concert_count = sum(1 for _, mf in media_files if mf.content_type == "concert_film")
        unrecognized = [fp.name for fp, mf in media_files if mf.content_type in ("unknown", "")]
        console.print()
        console.print(classification_summary_panel(
            total=len(media_files),
            festival_sets=festival_count,
            concerts=concert_count,
            unrecognized=unrecognized,
        ))
        return 0

    # Run pipeline
    all_results = run_pipeline(pipeline_files, progress)

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

    # Completion signal
    if not quiet:
        elapsed = time.monotonic() - start_time
        console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]")

    return 0


def _run_kodi_sync(all_results, pipeline_files, config, console, quiet):
    """Notify Kodi to refresh items that had changes affecting Kodi display."""
    from festival_organizer.kodi import KodiClient, sync_library

    RELEVANT_OPS = {"nfo", "art", "posters", "album_poster", "fanart"}
    video_exts = config.video_extensions
    changed_paths: list[Path] = []
    album_poster_folders: set[Path] = set()

    for (fp, _mf, ops), results in zip(pipeline_files, all_results):
        final_path = fp
        for op, result in zip(ops, results):
            if op.name == "organize" and result.status == "done":
                final_path = op.target

        for r in results:
            if r.status != "done":
                continue
            if r.name == "album_poster":
                # folder.jpg changed; all videos in that folder need refresh
                album_poster_folders.add(final_path.parent)
            elif r.name in RELEVANT_OPS:
                changed_paths.append(final_path)

    # Expand album_poster folders: add all video files in affected folders
    for folder in album_poster_folders:
        for sibling in folder.iterdir():
            if sibling.is_file() and sibling.suffix.lower() in video_exts:
                changed_paths.append(sibling)

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


def _run_audit_logos(root: Path, config, console, *,
                     verbose: bool = False, debug: bool = False) -> int:
    """Audit curated festival logo coverage for a library."""
    from festival_organizer.library import find_library_root

    library_root = find_library_root(root) if root.exists() else None
    if not library_root:
        print_error(f"not a CrateDigger library: {root}", console)
        return 1

    # Scan all media files for canonical festival names
    from festival_organizer.analyzer import analyse_file
    festivals_found: set[str] = set()
    if not verbose and not debug:
        with console.status("Scanning library for festivals...") as status:
            for video in root.rglob("*"):
                if video.suffix.lower() in (".mkv", ".mp4", ".webm") and video.is_file():
                    status.update(f"Analyzing {escape(video.name)}")
                    mf = analyse_file(video, root, config)
                    if mf.festival:
                        display = config.get_festival_display(mf.festival, mf.edition)
                        festivals_found.add(display)
    else:
        if verbose or debug:
            console.print("Scanning library for festivals...")
        for video in root.rglob("*"):
            if video.suffix.lower() in (".mkv", ".mp4", ".webm") and video.is_file():
                mf = analyse_file(video, root, config)
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
