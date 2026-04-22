"""Command-line interface with workflow-oriented subcommands."""
from __future__ import annotations

import json
import logging
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console
    from festival_organizer.config import Config
    from festival_organizer.models import MediaFile

import typer

from festival_organizer import paths
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
    AlbumArtistMbidsOperation,
    ChapterArtistMbidsOperation,
)
from festival_organizer.progress import ProgressPrinter, OrganizeContractProgress, EnrichContractProgress, OrganizeEnrichProgress
from festival_organizer.runner import run_pipeline
from festival_organizer.scanner import scan_folder
from festival_organizer.templates import render_folder, render_filename


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants for _run_check_impl
# ---------------------------------------------------------------------------

_CD_TOOLS: list[tuple[str, str, bool]] = [
    # (metadata attr name, display name, required)
    ("FFPROBE_PATH",     "ffprobe",     True),
    ("MEDIAINFO_PATH",   "mediainfo",   True),
    ("MKVEXTRACT_PATH",  "mkvextract",  True),
    ("MKVPROPEDIT_PATH", "mkvpropedit", True),
    ("MKVMERGE_PATH",    "mkvmerge",    True),
]

_CD_PACKAGES: list[str] = [
    "beautifulsoup4", "Pillow", "ftfy", "numpy", "requests", "rich", "typer",
]

# Asset probe for `--check`. Each entry is (label, resolver, description).
# The resolver is called at check time so tests can monkeypatch the paths
# module without needing to reload this list. Routed through
# ``festival_organizer.paths`` so the probe follows platformdirs layout.
_CD_ASSETS: list[tuple[str, Callable[[], Path], str]] = [
    ("config.toml",       lambda: paths.config_file(),       "user config"),
    ("festivals.json",    lambda: paths.festivals_file(),    "curated festival aliases"),
    ("artists.json",      lambda: paths.artists_file(),      "curated artist aliases"),
    ("artist_mbids.json", lambda: paths.artist_mbids_file(), "curated MBID overrides"),
]


# ---------------------------------------------------------------------------
# Shared type aliases (single source of truth for help text)
# ---------------------------------------------------------------------------

RootArg = Annotated[str, typer.Argument(help="File or folder to process")]
LibraryArg = Annotated[str, typer.Argument(help="Library folder to process")]
OutputOpt = Annotated[Optional[str], typer.Option("--output", "-o", help="Output folder")]
ConfigOpt = Annotated[Optional[str], typer.Option("--config", help="Path to config.toml")]
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


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version

        typer.echo(f"cratedigger {version('cratedigger')}")
        raise typer.Exit()


def _pick_version_line(output: str) -> str:
    """Return the most informative line from a tool's --version output.

    Prefers the first line that contains a digit (a version number). Falls back
    to the first non-empty line. Needed because some tools (mediainfo) print
    a banner on line 1 and the version on line 2.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in lines:
        if any(ch.isdigit() for ch in ln):
            return ln
    return lines[0] if lines else ""


def _run_check_impl(con: "Console") -> int:
    import subprocess
    from festival_organizer import metadata
    from festival_organizer.config import load_config
    from festival_organizer.metadata import get_install_hint
    from festival_organizer.frame_sampler import _HAS_CV2
    from importlib.metadata import version as pkg_version, PackageNotFoundError

    errors = warnings = 0

    # --- Tools ---
    con.print("\n[bold]Tools[/bold]")
    for attr, display, required in _CD_TOOLS:
        path = getattr(metadata, attr, None)
        if path is None:
            marker = "[red]\u2717[/red]" if required else "[yellow]![/yellow]"
            con.print(f"  {marker} {display:<14} not found")
            hint = get_install_hint(display)
            if hint:
                con.print(f"    [cyan]{hint}[/cyan]")
            if required:
                errors += 1
            else:
                warnings += 1
        else:
            try:
                r = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=5, check=False,
                )
                version_line = _pick_version_line(r.stdout or r.stderr or "")
                if version_line:
                    con.print(f"  [green]\u2713[/green] {display:<14} {version_line}")
                else:
                    marker = "[red]\u2717[/red]" if required else "[yellow]![/yellow]"
                    con.print(f"  {marker} {display:<14} version probe returned no output")
                    if required:
                        errors += 1
                    else:
                        warnings += 1
            except (OSError, subprocess.SubprocessError) as exc:
                marker = "[red]\u2717[/red]" if required else "[yellow]![/yellow]"
                con.print(f"  {marker} {display:<14} failed to run: {exc}")
                if required:
                    errors += 1
                else:
                    warnings += 1

    # cv2/numpy uses the already-computed _HAS_CV2 flag
    if _HAS_CV2:
        con.print("  [green]\u2713[/green] cv2/numpy")
    else:
        con.print("  [yellow]![/yellow] cv2/numpy      not found (optional, vision features)")
        con.print("    [cyan]Install with: pip install opencv-python numpy[/cyan]")
        warnings += 1

    # --- Config files ---
    con.print("\n[bold]Config[/bold]")
    for _label, resolve, desc in _CD_ASSETS:
        p = resolve()
        if p.is_file():
            con.print(f"  [green]\u2713[/green] {p}")
        else:
            con.print(f"  [yellow]![/yellow] {p}   not found (optional, {desc})")
            warnings += 1

    # --- Credentials ---
    con.print("\n[bold]Credentials[/bold]")
    try:
        config = load_config()

        email, password = config.tracklists_credentials
        if email and password:
            con.print("  [green]\u2713[/green] 1001TL       email + password configured")
        else:
            con.print("  [yellow]![/yellow] 1001TL       email or password missing (optional, tracklist enrichment)")
            warnings += 1

        cookie_path = paths.cookies_file()
        if cookie_path.is_file():
            con.print(f"  [green]\u2713[/green] 1001TL cookies  {cookie_path}")
        else:
            con.print("  [dim]\u007e[/dim] 1001TL cookies  not found, will be created on first login")

        fanart_key = config.fanart_personal_api_key or ""
        if fanart_key:
            con.print("  [green]\u2713[/green] fanart.tv    project + personal API key configured")
        else:
            con.print("  [dim]\u007e[/dim] fanart.tv    using built-in project API key (personal key not set)")

        if not config.kodi_enabled:
            con.print("  [dim]\u007e[/dim] Kodi         not configured, skipping")
        else:
            con.print(f"  [green]\u2713[/green] Kodi         host: {config.kodi_host}")

    except Exception as exc:
        con.print(f"  [red]\u2717[/red] Could not load config: {exc}")
        errors += 1

    # --- Python packages ---
    con.print("\n[bold]Python packages[/bold]")
    for pkg in _CD_PACKAGES:
        try:
            ver = pkg_version(pkg)
            con.print(f"  [green]\u2713[/green] {pkg:<20} {ver}")
        except PackageNotFoundError:
            con.print(f"  [red]\u2717[/red] {pkg:<20} not found")
            errors += 1

    # --- Summary ---
    con.print()
    if errors == 0 and warnings == 0:
        con.print("[green]All checks passed.[/green]")
    else:
        parts = []
        if errors:
            parts.append(f"[red]{errors} {'error' if errors == 1 else 'errors'}[/red]")
        if warnings:
            parts.append(f"[yellow]{warnings} {'warning' if warnings == 1 else 'warnings'}[/yellow]")
        con.print(", ".join(parts) + ".")

    return 1 if errors else 0


def _run_check() -> int:
    return _run_check_impl(make_console())


def _check_callback(value: bool) -> None:
    if value:
        raise typer.Exit(code=_run_check())


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version_flag: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    check_flag: bool = typer.Option(
        False,
        "--check",
        callback=_check_callback,
        is_eager=True,
        help="Verify tools, config, credentials, and Python packages, then exit.",
    ),
):
    """CrateDigger: Festival set & concert library manager."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise SystemExit(1)
    from festival_organizer.update_check import print_cached_update_notice
    print_cached_update_notice(make_console())


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
    move: Annotated[bool, typer.Option("--move", help="When importing (source != output): move files instead of copying. Ignored for in-place re-organize — in-place always uses atomic rename.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview what would happen without making changes")] = False,
    enrich: Annotated[bool, typer.Option("--enrich", help="Run all enrichment after organizing (use enrich command for selective operations)")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Organize files into the library layout.

    Action is chosen automatically:
      - in-place (source is the library or inside it): rename
      - importing (source disjoint from output): copy, or move with --move
      - --dry-run previews without changing anything
    """
    if dry_run and move:
        print("Error: --dry-run and --move cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    return _dispatch("organize", locals())


@app.command()
def enrich(
    root: LibraryArg,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    only: Annotated[Optional[str], typer.Option("--only", help="Comma-separated operations to run (nfo, art, fanart, posters, tags, chapter_artist_mbids, album_artist_mbids)")] = None,
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
    except (OSError, AttributeError, ValueError):
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
    except (OSError, AttributeError, ValueError):
        pass


def _cleanup_console() -> None:
    """Reset terminal state to prevent cross-process console corruption on Windows."""
    try:
        sys.stdout.write("\033[?25h")  # Show cursor (Rich Status/Live may hide it)
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError:
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
        try:
            from festival_organizer.update_check import refresh_update_cache
            refresh_update_cache()
        except BaseException:
            pass


def resolve_action(
    *, source: Path, output: Path, move: bool, dry_run: bool,
) -> str:
    """Decide the organize action from flags plus the source/output relationship.

    Returns one of: "dry_run", "rename", "move", "copy".

    The rule:
      - --dry-run trumps everything; preview only.
      - If source equals output (or is a descendant): the user is re-organizing
        within a library. Use atomic rename (same filesystem guaranteed).
      - If source is disjoint from output: the user is importing. --move clears
        the inbox after transfer; otherwise copy (safe default, leaves source
        intact for verification).
    """
    if dry_run:
        return "dry_run"
    if source_inside_or_equals_output(source, output):
        return "rename"
    return "move" if move else "copy"


def source_inside_or_equals_output(source: Path, output: Path) -> bool:
    """True when ``source`` is ``output`` or any descendant of it — the
    "reorganize in-place" signal."""
    try:
        src = source.resolve()
        out = output.resolve()
    except OSError:
        src = source
        out = output
    if src == out:
        return True
    try:
        src.relative_to(out)
        return True
    except ValueError:
        return False


def _analyse_parallel(
    files: list[Path],
    root: Path,
    config: Config,
    max_workers: int = 4,
    on_complete: Callable[[], None] | None = None,
) -> list[tuple[Path, MediaFile]]:
    """Analyse and classify files using a thread pool.

    Returns list of (Path, MediaFile) tuples in the same order as input.
    Spawns mediainfo/ffprobe subprocesses in parallel to overlap I/O.

    If on_complete is provided, it is called (from the main thread) each
    time a file finishes. Useful for progress reporting.
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
            if on_complete:
                on_complete()

    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Command logic (unchanged)
# ---------------------------------------------------------------------------

def _run_command(args: types.SimpleNamespace) -> int:
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
    paths.warn_if_legacy_paths_exist()

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

    # Resolve the organize action once from flags + source/output relationship.
    # This is the single source of truth the header, operation construction,
    # and post-pipeline cleanup all read.
    if args.command == "organize":
        action = resolve_action(
            source=root, output=output,
            move=getattr(args, "move", False),
            dry_run=getattr(args, "dry_run", False),
        )
    else:
        action = ""

    # Compute the human-readable action for the header. For dry-run, this is
    # what would happen if the user ran without --dry-run.
    if args.command == "organize":
        dry_run = getattr(args, "dry_run", False)
        header_action = action if not dry_run else (
            "move" if getattr(args, "move", False) else
            "rename" if source_inside_or_equals_output(root, output) else "copy"
        )
    else:
        header_action = ""

    # Organize safety: confirm when source is inside existing library
    if args.command == "organize" and not getattr(args, "dry_run", False) and library_root and not explicit_output:
        try:
            root.resolve().relative_to(library_root.resolve())
            is_inside_library = True
        except ValueError:
            is_inside_library = False

        if is_inside_library and not getattr(args, "yes", False):
            print(f"Re-organizing library at {library_root} "
                  f"with layout '{config.default_layout}'. "
                  f"Files will be renamed in place to match the layout.",
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
    if args.command == "organize" and not getattr(args, "enrich", False):
        progress = OrganizeContractProgress(
            total=0, console=console, quiet=quiet, verbose=verbose,
            output_root=output,
            dry_run=getattr(args, "dry_run", False),
            action=header_action,
            layout=config.default_layout,
        )
    elif args.command == "organize" and getattr(args, "enrich", False):
        organize_prog = OrganizeContractProgress(
            total=0, console=console, quiet=quiet, verbose=verbose,
            output_root=output,
            dry_run=getattr(args, "dry_run", False),
            action=header_action,
            layout=config.default_layout,
        )
        enrich_prog = EnrichContractProgress(
            total=0, console=console, quiet=quiet, verbose=verbose,
        )
        progress = OrganizeEnrichProgress(organize_prog, enrich_prog)
    elif args.command == "enrich":
        progress = EnrichContractProgress(
            total=0, console=console, quiet=quiet, verbose=verbose,
        )
    else:
        progress = ProgressPrinter(total=0, console=console, quiet=quiet, verbose=verbose)
    use_contract = isinstance(progress, (OrganizeContractProgress, EnrichContractProgress, OrganizeEnrichProgress))
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
        dry_run = getattr(args, "dry_run", False)
        command_label = f"Organize (dry run, {header_action})" if dry_run else "Organize"
        header_rows = {
            "Source": str(root),
            "Output": str(output),
            "Layout": config.default_layout,
            "Action": header_action,
            "Files": str(len(files)),
        }
        if getattr(args, "enrich", False):
            header_rows["Enrich"] = "yes"

    if args.command in ("enrich", "organize"):
        if getattr(args, "kodi_sync", False):
            header_rows["Kodi sync"] = "yes (flag)"
        elif config.kodi_enabled:
            header_rows["Kodi sync"] = "yes (config)"

    progress.print_header(command=command_label, rows=header_rows, missing_tools=missing_tools)

    if not files:
        console.print("Nothing to do.")
        return 0

    progress.total = len(files)

    # Analyze + classify (parallel)
    if not quiet and not verbose and not debug:
        from rich.progress import Progress, BarColumn, MofNCompleteColumn, TextColumn
        with Progress(
            TextColumn("Analyzing"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as pbar:
            task_id = pbar.add_task("analyze", total=len(files))
            media_files = _analyse_parallel(
                files, root, config,
                on_complete=lambda: pbar.advance(task_id),
            )
    else:
        if not quiet and (verbose or debug):
            console.print(f"Analyzing {len(files)} files...")
        media_files = _analyse_parallel(files, root, config)

    # Build operations per file
    force = getattr(args, "regenerate", False)
    only = set()
    if getattr(args, "only", None):
        only = {v.strip() for v in args.only.split(",")}
        valid_ops = {"nfo", "art", "fanart", "posters", "tags", "chapter_artist_mbids", "album_artist_mbids"}
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
        should_album_poster = (args.command == "enrich" and (not only or "posters" in only)) or \
                              (args.command == "organize" and getattr(args, "enrich", False))
        if should_album_poster:
            images_ttl = config.cache_ttl.get("images_days", 90)
            album_poster_op = AlbumPosterOperation(config, force=force, library_root=output,
                                                    ttl_days=images_ttl)

    # Load DJ cache once for group member expansion in NFO tags
    dj_cache = None
    try:
        from festival_organizer.tracklists.dj_cache import DjCache
        dj_cache = DjCache()
    except (ImportError, OSError, json.JSONDecodeError) as e:
        logger.debug("DjCache init skipped: %s", e)

    for fp, mf in media_files:
        ops: list = []

        if getattr(args, "dry_run", False):
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            if isinstance(progress, (OrganizeContractProgress, OrganizeEnrichProgress)):
                # file_preview is only defined on the organize-side progress
                # types. The outer `args.dry_run` guard ensures we are in
                # `organize` here (enrich/identify/audit-logos have no
                # --dry-run flag), so this isinstance is always True in
                # practice; the explicit check documents the invariant for
                # type checkers and future refactors.
                progress.file_preview(source=fp, media_file=mf, target=target)
            elif isinstance(progress, ProgressPrinter):
                # Fallback for non-contract progress. Unreachable in practice
                # when args.dry_run=True (organize always installs one of the
                # contract types above), but kept for defensive completeness.
                progress.file_start(fp, target_folder + "/" + target_name)
                progress.file_done([])
            # EnrichContractProgress is not reachable in this branch: it only
            # ships with the `enrich` command, which has no --dry-run flag.
            continue

        if args.command == "organize":
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            ops.append(OrganizeOperation(target=target, action=action))

            if getattr(args, "enrich", False):
                ops.append(NfoOperation(config, dj_cache=dj_cache))
                ops.append(ArtOperation())
                if fanart_op:
                    ops.append(fanart_op)
                ops.append(PosterOperation(config))
                if album_poster_op:
                    ops.append(album_poster_op)
                ops.append(TagsOperation())
                ops.append(ChapterArtistMbidsOperation(config=config, force=force))
                ops.append(AlbumArtistMbidsOperation(config=config, force=force))

        elif args.command == "enrich":
            if not only or "nfo" in only:
                ops.append(NfoOperation(config, force=force, dj_cache=dj_cache))
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
            if not only or "chapter_artist_mbids" in only:
                ops.append(ChapterArtistMbidsOperation(config=config, force=force))
            if not only or "album_artist_mbids" in only:
                ops.append(AlbumArtistMbidsOperation(config=config, force=force))

        pipeline_files.append((fp, mf, ops))

    if getattr(args, "dry_run", False):
        if isinstance(progress, OrganizeEnrichProgress):
            elapsed = time.monotonic() - start_time
            progress.organize.print_summary(elapsed_s=elapsed)
        elif use_contract:
            elapsed = time.monotonic() - start_time
            progress.print_summary(elapsed_s=elapsed)
        else:
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
    if isinstance(progress, (EnrichContractProgress, OrganizeEnrichProgress)):
        from festival_organizer.console import StepProgress, suppression_enabled
        suppressed = suppression_enabled(console, quiet=quiet, verbose=verbose, debug=debug)
        step = StepProgress(console, enabled=not suppressed)
        with step:
            all_results = run_pipeline(pipeline_files, progress, step_progress=step)
    else:
        all_results = run_pipeline(pipeline_files, progress)

    # Post-pipeline: folder-level integrity after organize.
    #   - "move" across libraries: remove emptied source folders (historical).
    #   - "rename" (in-place re-organize): when a file renames into a different
    #     folder and leaves its source folder empty of videos, follow
    #     folder.jpg/fanart.jpg to the new folder and then remove the empty
    #     source folder.
    if args.command == "organize":
        if action in ("move", "rename"):
            from festival_organizer.library import (
                cleanup_empty_dirs, migrate_folder_artefacts,
            )
            if action == "rename":
                moves: list[tuple[Path, Path]] = []
                for (orig_path, _mf, ops) in pipeline_files:
                    for op in ops:
                        if op.name == "organize" and getattr(op, "target", None):
                            src_dir = orig_path.parent
                            tgt_dir = op.target.parent
                            if src_dir.resolve() != tgt_dir.resolve():
                                moves.append((src_dir, tgt_dir))
                if moves:
                    migrate_folder_artefacts(
                        moves, video_exts=set(config.video_extensions)
                    )
                cleanup_empty_dirs(output)
            elif root.resolve() != output.resolve():
                cleanup_empty_dirs(root)

    # Pass unresolved artist names to enrich progress for summary
    if isinstance(progress, EnrichContractProgress):
        from festival_organizer.fanart import unresolved_artist_names
        progress._unresolved_artists = unresolved_artist_names
    elif isinstance(progress, OrganizeEnrichProgress):
        from festival_organizer.fanart import unresolved_artist_names
        progress.enrich._unresolved_artists = unresolved_artist_names

    if isinstance(progress, OrganizeEnrichProgress):
        elapsed = time.monotonic() - start_time
        progress.organize.print_summary(elapsed_s=elapsed)
        progress.enrich.print_summary(elapsed_s=elapsed)
    elif use_contract:
        elapsed = time.monotonic() - start_time
        progress.print_summary(elapsed_s=elapsed)
    else:
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
        _run_kodi_sync(all_results, pipeline_files, config, console, quiet,
                       verbose=verbose, debug=debug)

    # Completion signal
    if not quiet and not use_contract:
        elapsed = time.monotonic() - start_time
        console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]")

    return 0


def _run_kodi_sync(
    all_results: list[list],
    pipeline_files: list[tuple],
    config: Config,
    console: "Console",
    quiet: bool,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """Notify Kodi to refresh items that had changes affecting Kodi display."""
    from festival_organizer.kodi import KodiClient, sync_library

    RELEVANT_OPS = {"nfo", "art", "posters", "fanart"}
    video_exts = config.video_extensions
    changed_paths: list[Path] = []
    album_poster_folders: set[Path] = set()
    kodi_logger = logging.getLogger("festival_organizer.kodi")

    for (fp, _mf, ops), results in zip(pipeline_files, all_results):
        final_path = fp
        for op, result in zip(ops, results):
            if op.name == "organize" and result.status == "done":
                final_path = op.target

        for r in results:
            if r.status != "done":
                continue
            if r.display_name == "album_poster":
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
        kodi_logger.debug(
            "Kodi sync: no kodi-affecting changes (%d files processed, "
            "all skipped or non-relevant); nothing to refresh",
            len(pipeline_files),
        )
        return

    try:
        client = KodiClient(
            host=config.kodi_host,
            port=config.kodi_port,
            username=config.kodi_username,
            password=config.kodi_password,
        )
        path_mapping = config.kodi_settings.get("path_mapping")
        from festival_organizer.console import suppression_enabled
        suppressed = suppression_enabled(console, quiet=quiet, verbose=verbose, debug=debug)
        sync_library(client, changed_paths, console, quiet,
                     path_mapping=path_mapping, suppressed=suppressed)
    except Exception as e:
        logging.getLogger("festival_organizer.kodi").warning(
            "Kodi sync failed: %s", e
        )
        if not quiet:
            console.print(f"[yellow]Kodi sync failed: {e}[/yellow]")


def _run_audit_logos(root: Path, config: Config, console: Console, *,
                     verbose: bool = False, debug: bool = False) -> int:
    """Audit curated festival logo coverage for a library."""
    from festival_organizer.library import find_library_root

    library_root = find_library_root(root) if root.exists() else None
    if not library_root:
        print_error(f"not a CrateDigger library: {root}", console)
        return 1

    # Scan all media files for canonical festival names
    if not verbose and not debug:
        with console.status("Scanning for media files..."):
            videos = [v for v in root.rglob("*")
                      if v.suffix.lower() in (".mkv", ".mp4", ".webm") and v.is_file()]
    else:
        if verbose or debug:
            console.print("Scanning library for festivals...")
        videos = [v for v in root.rglob("*")
                  if v.suffix.lower() in (".mkv", ".mp4", ".webm") and v.is_file()]

    festivals_found: set[str] = set()
    if videos:
        analyzed = _analyse_parallel(videos, root, config)
        for _fp, mf in analyzed:
            if mf.festival:
                display = config.get_festival_display(mf.festival, mf.edition)
                festivals_found.add(display)

    # Check logo availability for each festival
    logo_dirs = [
        library_root / ".cratedigger" / "festivals",
        paths.festivals_logo_dir(),
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
        user_festivals = paths.festivals_logo_dir()
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
