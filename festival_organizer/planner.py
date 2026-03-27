"""Plan builder: creates FileAction list from analysed MediaFiles."""
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import FileAction, MediaFile
from festival_organizer.templates import render_filename, render_folder


def plan_actions(
    files: list[MediaFile],
    output_root: Path,
    config: Config,
    action: str = "move",
    layout_name: str | None = None,
    generate_nfo: bool = False,
    extract_art: bool = False,
    generate_posters: bool = False,
    embed_tags: bool = False,
) -> list[FileAction]:
    """Build a list of FileActions for all files.

    Args:
        files: Analysed MediaFile objects
        output_root: Target root directory
        config: Configuration
        action: "move", "copy", or "rename"
        layout_name: Override layout (default uses config.default_layout)
        generate_nfo: Whether to generate Kodi NFO files
        extract_art: Whether to extract cover art
        generate_posters: Whether to generate set poster images
        embed_tags: Whether to embed Plex tags via mkvpropedit
    """
    actions = []

    for mf in files:
        folder_rel = render_folder(mf, config, layout_name)
        filename = render_filename(mf, config)

        if action == "rename":
            # Rename in place — keep original directory
            target = mf.source_path.parent / filename
        else:
            target = output_root / folder_rel / filename

        actions.append(FileAction(
            source=mf.source_path,
            target=target,
            media_file=mf,
            action=action,
            generate_nfo=generate_nfo,
            extract_art=extract_art,
            generate_posters=generate_posters,
            embed_tags=embed_tags,
        ))

    return actions
