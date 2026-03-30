#!/usr/bin/env python3
"""One-off migration: rename 1001TRACKLISTS_* tags to CRATEDIGGER_1001TL_* in MKV files.

Usage:
    python scripts/migrate_tags.py <folder> [--dry-run]

Scans recursively for .mkv/.webm files, reads existing tags, renames
1001TRACKLISTS_* to CRATEDIGGER_1001TL_*, and writes back. Old tag names
are removed. Standard tags (ARTIST, TITLE, DATE_RELEASED) are untouched.

Requires mkvextract and mkvpropedit in PATH or configured in CrateDigger.
"""
import argparse
import sys
from pathlib import Path

# Add project root to path so we can import festival_organizer
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from festival_organizer import metadata
from festival_organizer.metadata import configure_tools
from festival_organizer.config import Config
from festival_organizer.mkv_tags import extract_all_tags, write_merged_tags

TAG_RENAME_MAP = {
    "1001TRACKLISTS_URL": "CRATEDIGGER_1001TL_URL",
    "1001TRACKLISTS_TITLE": "CRATEDIGGER_1001TL_TITLE",
    "1001TRACKLISTS_ID": "CRATEDIGGER_1001TL_ID",
    "1001TRACKLISTS_DATE": "CRATEDIGGER_1001TL_DATE",
    "1001TRACKLISTS_GENRES": "CRATEDIGGER_1001TL_GENRES",
    "1001TRACKLISTS_EVENT_ARTWORK": "CRATEDIGGER_1001TL_EVENT_ARTWORK",
    "1001TRACKLISTS_DJ_ARTWORK": "CRATEDIGGER_1001TL_DJ_ARTWORK",
}


def migrate_file(filepath: Path, dry_run: bool = False) -> str:
    """Migrate tags in a single MKV file. Returns status string."""
    tags_root = extract_all_tags(filepath)
    if tags_root is None:
        return "no-tags"

    # Scan all Tag blocks for old-style names
    renames: dict[int, dict[str, str]] = {}  # TTV -> {new_name: value}
    removes: dict[int, list[str]] = {}       # TTV -> [old_names to remove]

    for tag in tags_root.findall("Tag"):
        targets = tag.find("Targets")
        ttv = 50  # default
        if targets is not None:
            ttv_el = targets.find("TargetTypeValue")
            if ttv_el is not None and ttv_el.text:
                ttv = int(ttv_el.text)

        for simple in tag.findall("Simple"):
            name_el = simple.find("Name")
            if name_el is None or name_el.text is None:
                continue
            old_name = name_el.text
            if old_name in TAG_RENAME_MAP:
                new_name = TAG_RENAME_MAP[old_name]
                string_el = simple.find("String")
                value = string_el.text if string_el is not None and string_el.text else ""
                if value:
                    renames.setdefault(ttv, {})[new_name] = value
                    removes.setdefault(ttv, []).append(old_name)

    if not renames:
        return "already-migrated"

    if dry_run:
        for ttv, pairs in renames.items():
            for new_name, value in pairs.items():
                old_name = [k for k, v in TAG_RENAME_MAP.items() if v == new_name][0]
                print(f"    {old_name} -> {new_name} = {value[:80]}")
        return "would-migrate"

    # Step 1: Write new tag names with values
    ok = write_merged_tags(filepath, renames)
    if not ok:
        return "write-error"

    # Step 2: Remove old tag names by re-extracting, removing old Simple elements, rewriting
    tags_root = extract_all_tags(filepath)
    if tags_root is None:
        return "migrated-partial"

    removed_any = False
    for tag in tags_root.findall("Tag"):
        targets = tag.find("Targets")
        ttv = 50
        if targets is not None:
            ttv_el = targets.find("TargetTypeValue")
            if ttv_el is not None and ttv_el.text:
                ttv = int(ttv_el.text)

        if ttv not in removes:
            continue

        old_names = removes[ttv]
        for simple in tag.findall("Simple"):
            name_el = simple.find("Name")
            if name_el is not None and name_el.text in old_names:
                tag.remove(simple)
                removed_any = True

    if removed_any:
        # Write the cleaned XML back (with old names removed)
        import xml.etree.ElementTree as ET
        import tempfile
        import subprocess

        # Strip track-targeted tags before writing
        for tag in tags_root.findall("Tag"):
            tgt = tag.find("Targets")
            if tgt is not None and tgt.find("TrackUID") is not None:
                tags_root.remove(tag)

        ET.indent(tags_root, space="  ")
        xml_str = ET.tostring(tags_root, encoding="unicode", xml_declaration=True)

        tag_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".xml", delete=False, encoding="utf-8"
            ) as f:
                f.write(xml_str)
                tag_file = f.name

            mkvpropedit = metadata.MKVPROPEDIT_PATH
            assert mkvpropedit is not None
            result = subprocess.run(
                [mkvpropedit, str(filepath), "--tags", f"global:{tag_file}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return "cleanup-error"
        finally:
            if tag_file:
                import os
                try:
                    os.unlink(tag_file)
                except OSError:
                    pass

    return "migrated"


def main():
    parser = argparse.ArgumentParser(description="Migrate 1001TRACKLISTS_* tags to CRATEDIGGER_1001TL_*")
    parser.add_argument("folder", type=str, help="Folder to scan recursively")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying files")
    args = parser.parse_args()

    root = Path(args.folder)
    if not root.exists():
        print(f"Error: {root} does not exist", file=sys.stderr)
        return 1

    # Initialize tools — use empty config to auto-detect paths
    # (avoids picking up Windows tool_paths from library config)
    config = Config({})
    configure_tools(config)

    if not metadata.MKVPROPEDIT_PATH:
        print("Error: mkvpropedit not found. Install MKVToolNix.", file=sys.stderr)
        return 1
    if not metadata.MKVEXTRACT_PATH:
        print("Error: mkvextract not found. Install MKVToolNix.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("DRY RUN — no files will be modified\n")

    files = sorted(root.rglob("*"))
    media_files = [f for f in files if f.suffix.lower() in (".mkv", ".webm")]
    print(f"Found {len(media_files)} MKV/WEBM file(s) in {root}\n")

    stats = {"migrated": 0, "already-migrated": 0, "no-tags": 0,
             "would-migrate": 0, "error": 0}

    for i, fp in enumerate(media_files, 1):
        rel = fp.relative_to(root)
        print(f"  [{i}/{len(media_files)}] {rel}")
        status = migrate_file(fp, dry_run=args.dry_run)

        if "error" in status:
            print(f"    ERROR: {status}")
            stats["error"] += 1
        elif status == "already-migrated":
            print(f"    (already migrated)")
            stats["already-migrated"] += 1
        elif status == "no-tags":
            print(f"    (no tags)")
            stats["no-tags"] += 1
        elif status == "migrated":
            print(f"    OK")
            stats["migrated"] += 1
        elif status == "would-migrate":
            stats["would-migrate"] += 1

    print(f"\n{'DRY RUN ' if args.dry_run else ''}Summary:")
    if args.dry_run:
        print(f"  Would migrate: {stats['would-migrate']}")
    else:
        print(f"  Migrated:         {stats['migrated']}")
    print(f"  Already migrated: {stats['already-migrated']}")
    print(f"  No tags:          {stats['no-tags']}")
    if stats["error"]:
        print(f"  Errors:           {stats['error']}")

    return 1 if stats["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
