# Album NFO Cleanup and Per-Video Fanart

## Context

Investigation into enriching album.nfo with tags and fanart references revealed that
Kodi does NOT read album.nfo for music videos. Kodi's VideoInfoScanner only reads
per-video .nfo files (e.g. `video.nfo`). The `album.nfo` format is exclusively used
by Kodi's music library scanner for audio albums.

This means `album_nfo.py` and its tests are dead code that was never wired into the
pipeline and would have no effect in Kodi even if it were.

## Decisions

1. **Per-video NFO fanart**: Already implemented. Each video's `.nfo` includes
   `<fanart><thumb>stem-thumb.jpg</thumb></fanart>` referencing its own thumbnail.
   Kodi supports multiple `<thumb>` entries inside `<fanart>`, but own-thumb-only
   is sufficient.

2. **Album NFO**: Remove entirely. `album_nfo.py`, `test_album_nfo.py`, and all
   references (library.py FOLDER_SIDECARS, operations.py FOLDER_LEVEL_FILES).

3. **Per-video tags**: Current tags (content_type, festival, location) are sufficient.
   No additional tags needed.

4. **Fanart source**: Thumbnails from set frames are the best source. Fanart.tv
   backgrounds are often old. Curated festival logos are too small (~600px).
   The `.cratedigger/` cache remains a pure input for poster generation only.

## Changes

### Remove
- `festival_organizer/album_nfo.py`
- `tests/test_album_nfo.py`
- `"album.nfo"` from `library.py` FOLDER_SIDECARS
- `"album.nfo"` from `operations.py` FOLDER_LEVEL_FILES

### No changes needed
- Per-video NFO fanart (already shipped)
- Per-video tags (already complete)
- Poster generation pipeline (unaffected)

## Verification
- `pytest` full suite passes after removal
- `grep -r album_nfo` returns no hits
- `grep -r "album.nfo"` only returns this design doc
