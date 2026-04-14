# identify

Match your recordings against 1001Tracklists and embed track listings and chapter markers
directly into your video files.

## What this is for

When you have a recording of a DJ set, you usually know roughly what it is, but the file
has no detailed track-by-track information inside it. The `identify` command fixes that.

It searches [1001Tracklists](https://www.1001tracklists.com) (a community website that
logs exactly which tracks DJs played during sets, with timestamps) and embeds that
information into your MKV file. The result is a file with named chapter markers, one per
track, so media players can jump to any track in the set, and so the rest of the CrateDigger
pipeline has rich metadata to work with.

**A 1001Tracklists account is required.** The `identify` command always logs in before
processing. Without credentials, it exits with an error. See
[Do I need an account?](../tracklists.md#do-i-need-an-account) for what you still get if
you skip this step.

## Before you start

- A [1001Tracklists](https://www.1001tracklists.com) account (free)
- Credentials set in your config or as environment variables. See
  [Tracklists integration](../tracklists.md#account-setup).
- MKVToolNix installed (`mkvpropedit` must be on your PATH). See
  [Getting started](../getting-started.md#required-tools).
- Your recordings should be in MKV or WEBM format. `identify` only processes those formats.
  Other file types are skipped silently.

## Usage

```bash
cratedigger identify <folder_or_file> [options]
```

`<folder_or_file>` can be:

- A single MKV or WEBM file
- A folder. CrateDigger scans it for all MKV and WEBM files and processes each one.

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--tracklist <value>` | `-t` | (none) | Tracklist URL, numeric 1001TL ID, or a free-text search query to use instead of auto-searching |
| `--auto` | | off | Auto-select the best match without prompting. Skips files where confidence is too low. |
| `--preview` | | off | Show the matched chapter list without embedding anything. Read-only. |
| `--regenerate` / `--fresh` | | off | Ignore stored results and re-identify the file, even if chapters are already embedded |
| `--delay <seconds>` | | 5 | Pause between files to avoid rate-limiting |
| `--config <path>` | | (none) | Path to a config.json file |
| `--quiet` | `-q` | off | Suppress per-file progress output |
| `--verbose` | `-v` | off | Show detailed progress and decisions |
| `--debug` | | off | Show cache hits, retries, and internal mechanics |

## Step-by-step: what happens when you run identify

### 1. CrateDigger builds a search query

If you did not provide `--tracklist`, CrateDigger builds the search text from the
**filename only**. It strips noise (codec labels, resolution tags, YouTube IDs in brackets)
and expands known festival abbreviations. For example, "AMF" becomes
"Amsterdam Music Festival" and "EDC" becomes "Electric Daisy Carnival". These expansions
come from your [festivals.json](../festivals.md) aliases.

The file's actual duration (read from the video stream via MediaInfo) and year (from an
embedded date tag if present) are passed separately to help rank results. They are not
part of the search text.

### 2. Results are ranked and shown

CrateDigger queries 1001Tracklists and scores each result based on:

- How well the artist name matches
- How well the festival or event name matches
- Whether the year matches
- How close the tracklist duration is to your file duration
- Whether artist or source names appear in CrateDigger's DJ cache

Results are ranked by score, highest first. Example:

```
Analyzing 1 file...
  Tiësto - Live at We Belong Here Miami 2026 [2EQGqEvLAuE].mkv (2h 18m)

Search: "Tiesto We Belong Here Miami 2026"

Top matches:
  #   Score  Date        Duration  Title
  1   314    2026-03-01  2h 19m    Tiësto @ We Belong Here, Miami 2026
  2   186    2026-03-01  0h 58m    Tiësto @ Main Stage, We Belong Here Miami 2026 (Radio Edit)
  3   142    2025-02-28  1h 45m    Tiësto @ We Belong Here 2025
  4   121    2024-11-15  2h 02m    Tiësto @ EDC Orlando 2024
  5   98     2023-08-12  1h 30m    Tiësto @ Tomorrowland 2023

Select [1-5, 0=skip]: 1
```

A higher score means a stronger match. The gap between the top result and second place
matters more than the raw score. A large gap means CrateDigger is more confident in the
top result.

Type a number to select that tracklist, or `0` to skip the file.

### 3. Chapters and metadata are embedded

Once you confirm a match, CrateDigger:

1. Fetches the full tracklist from 1001Tracklists
2. Parses each track entry into a chapter with a timestamp and name
3. Embeds the chapters into your MKV file using `mkvpropedit`
4. Writes metadata tags into the file:
   - **Album-level tags**: tracklist URL, title, ID, date, genres, stage name, venue,
     festival, country, artist names, and DJ artwork URL
   - **Per-chapter tags**: for each track, performer name(s), track title, label, and genre

These tags are later read by the [`enrich`](enrich.md) command to generate artwork, NFO
files, and resolve MusicBrainz artist IDs.

If the tracklist has fewer than 2 chapters (for example, a tracklist with only a single
entry), CrateDigger skips the embed. A single chapter provides no navigation value.

```
Selected: Tiësto @ We Belong Here, Miami 2026 (2026-03-01)
Fetching tracklist... 38 tracks
Embedding chapters and tags...
  Chapters: 38 written
  Album-level tags: 14 written
  Per-chapter tags: 38 written
Done.
```

## What changes in your files

`identify` modifies only the files it processes. For each matched file:

- Chapter markers are embedded (one per track, with track name and timestamp)
- Album-level metadata tags are written (tracklist source information, artist list, genres)
- Per-chapter metadata tags are written (track title, performer, label, genre, one set per chapter)

No files are created, moved, or copied. The original video stream and audio are untouched.
Only the metadata section of the MKV file changes.

## Auto mode

With `--auto`, CrateDigger picks the top result automatically without prompting. It only
does this when it is confident:

- The top result must score **150 or higher**
- The gap between the top result and the second result must be **20 or more**

If either threshold is not met, the file is skipped and left for a later interactive pass.
This makes `--auto` safe for batch processing. When CrateDigger is unsure, it skips rather
than guessing.

To make auto mode the default without typing `--auto` every time, set `auto_select: true`
in your [config](../configuration.md#tracklists).

## Providing a tracklist directly

If you already know which tracklist page matches your recording, pass it with `--tracklist`:

```bash
# Full URL
cratedigger identify recording.mkv --tracklist "https://www.1001tracklists.com/tracklist/xyz"

# Numeric tracklist ID
cratedigger identify recording.mkv --tracklist 1234567

# Free-text query (overrides the auto-generated query)
cratedigger identify recording.mkv --tracklist "Tiesto We Belong Here Miami 2026"
```

Note: credentials are still required even when providing a URL directly.

## Re-identifying files

By default, if a file already has a stored tracklist URL from a previous run, CrateDigger
reuses it rather than searching again.

- **Interactive mode:** you are prompted to use the stored URL, skip the file, or search again
- **Auto mode:** the stored URL is used automatically

Use `--regenerate` (also accepted as `--fresh`) to ignore stored results and start fresh:

```bash
cratedigger identify ~/Music/Library/ --regenerate --auto
```

This is also useful after a CrateDigger update that adds new tag types. `--regenerate`
forces a full re-tag even when the chapter structure has not changed.

**Re-running periodically is worthwhile.** 1001Tracklists is a community database that
improves over time. A tracklist that had unidentified tracks or missing metadata when you
first ran `identify` may be much more complete a few months later, with more tracks matched,
artist IDs resolved, and labels filled in. Running `identify --auto` on your library every
few months picks up those improvements automatically. Files with a stored tracklist URL are
re-fetched from 1001Tracklists and updated if anything changed; files without a stored URL
are searched and auto-selected if CrateDigger is confident enough; everything else is left
alone.

### Self-healing

If a file has chapters but is missing some expected per-chapter tags (for example, files
identified with an older version of CrateDigger), the full tagging pass runs automatically
on the next `identify` run. You do not need `--regenerate` for this. CrateDigger detects
the gap and fills it in.

## Preview mode

`--preview` shows you what chapters would be embedded without writing anything to disk.
Useful to check a match before committing:

```bash
cratedigger identify recording.mkv --preview
```

## Common examples

**Identify a folder interactively (the default workflow):**

```bash
cratedigger identify ~/Downloads/sets/
```

CrateDigger processes each file one at a time, shows you matches, and waits for your selection.

**Batch process a folder with auto-selection:**

```bash
cratedigger identify ~/Downloads/sets/ --auto
```

Good for large batches. Well-named files get matched automatically; ambiguous ones are
skipped so you can handle them manually later.

**Pass a tracklist URL to skip searching:**

```bash
cratedigger identify "Martin Garrix @ AMF 2024.mkv" \
  --tracklist "https://www.1001tracklists.com/tracklist/abc123"
```

**Preview chapters for a single file before embedding:**

```bash
cratedigger identify recording.mkv --preview
```

**Re-identify files that were already processed:**

```bash
cratedigger identify ~/Downloads/sets/ --regenerate
```

## Common problems

**"Error: credentials required"**

Your 1001Tracklists email and password are not configured. Set them in
`~/.cratedigger/config.json` under `tracklists.email` and `tracklists.password`, or via the
environment variables `TRACKLISTS_EMAIL` and `TRACKLISTS_PASSWORD`. See
[Tracklists: account setup](../tracklists.md#account-setup).

**No results found for a file**

CrateDigger could not find a matching tracklist. Try:

- Pass a manual search query with `--tracklist "artist name event year"`
- Pass the tracklist URL directly if you find it on 1001Tracklists
- Check that the filename contains recognizable artist and event names

**File is skipped in auto mode**

The top result scored below 150, or the gap to the second result was less than 20. Run the
same folder interactively (without `--auto`) to see the matches and pick manually.

**Chapters not embedded (file is not MKV or WEBM)**

Only MKV and WEBM files support chapter embedding. MP4 and other formats are skipped.
Convert your file to MKV first with FFmpeg or MKVToolNix if needed.

**Tracklist has fewer than 2 tracks**

If the matched tracklist only has one entry, CrateDigger skips the embed. A single chapter
is not useful for navigation.

## Advanced details

### Tag structure

`identify` writes two types of tags into the MKV container:

- **Album-level tags (TargetTypeValue=70):** Set-wide information including the 1001Tracklists
  URL, tracklist title and ID, date, genre list, stage, venue, festival, country, source type,
  artist names, and DJ artwork URL. These are stored in the `CRATEDIGGER_1001TL_*` namespace.

- **Per-chapter tags (TargetTypeValue=30):** One tag block per chapter containing performer
  name(s), performer slugs, performer display names, track title, label, and genre.

The `enrich` command's `chapter_artist_mbids` and `album_artist_mbids` operations read
these tags later to resolve MusicBrainz IDs. See the
[tag reference](../tag-reference.md) for the full list.

### Rate limiting

CrateDigger waits between files (default: 5 seconds) to avoid hitting 1001Tracklists rate
limits. Change this with `--delay <seconds>` or by setting `delay_seconds` in your config.

## What to do next

After identifying your files, run [`organize`](organize.md) to move them into your library
structure, then [`enrich`](enrich.md) to add artwork, posters, and NFO files.
