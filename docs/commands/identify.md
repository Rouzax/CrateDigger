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

Results are ranked by score, highest first. A higher score means a stronger match. The gap
between the top result and second place matters more than the raw score; a large gap means
CrateDigger is more confident in the top result.

In interactive mode you see a numbered table of candidates and a prompt:

```
Top matches:
  #   Score  Date        Duration  Title
  1   314    2026-03-01  2h 19m    Tiësto @ We Belong Here, Miami 2026
  2   186    2026-03-01  0h 58m    Tiësto @ Main Stage, We Belong Here Miami 2026 (Radio Edit)
  3   142    2025-02-28  1h 45m    Tiësto @ We Belong Here 2025
  4   121    2024-11-15  2h 02m    Tiësto @ EDC Orlando 2024
  5   98     2023-08-12  1h 30m    Tiësto @ Tomorrowland 2023

Select (1-5, or 0 to skip): 1
```

Type a number to select that tracklist, or `0` to skip the file.

### 3. Chapters and metadata are embedded

Once you confirm a match, CrateDigger:

1. Fetches the full tracklist from 1001Tracklists
2. Parses each track entry into a chapter with a timestamp and name
3. Embeds the chapters into your MKV file using `mkvpropedit`
4. Writes metadata tags into the file:
   - **Album-level tags**: tracklist URL, title, ID, date, genres, stage name, venue,
     festival, country, free-text location, artist names, and DJ artwork URL
   - **Per-chapter tags**: for each track, performer name(s), track title, label, and genre

These tags are later read by the [`enrich`](enrich.md) command to generate artwork, NFO
files, and resolve MusicBrainz artist IDs.

If the tracklist has fewer than 2 chapters (for example, a tracklist with only a single
entry), CrateDigger skips the embed. A single chapter provides no navigation value.

## What you see when it runs

For each file, CrateDigger prints one verdict line: a padded badge, the file position, the
filename, a short note, and how long that file took. A transient spinner shows the current
step (sign-in, search, fetch, embed, throttle) while each file is processed; it disappears
as soon as the verdict line is printed. At the end a summary panel shows totals and lists
any files that did not get embedded.

A real batch of five festival recordings looks like this:

```
[ done        ] [1/5] Tiesto - Live at We Belong Here Miami 2026.mkv  ->  Tiesto @ We Belong Here, Miami 2026 (2026-03-01) - 38 tracks  (12.4s)
[ done        ] [2/5] Martin Garrix @ AMF 2026.webm  ->  Martin Garrix @ Amsterdam Music Festival 2026 (2026-10-18) - 24 tracks  (9.8s)
[ up-to-date  ] [3/5] David Guetta @ Tomorrowland 2026.mkv  ->  already embedded (stored URL)  (2.1s)
[ skipped     ] [4/5] unknown_set_001.mkv  ->  low confidence (score 84)  (6.5s)
[ done        ] [5/5] Armin van Buuren @ ASOT 2026.mkv  ->  Armin van Buuren @ A State of Trance 2026 (2026-02-15) - 42 tracks  (11.2s)

Summary
  added: 3  updated: 0  up_to_date: 1  skipped: 1  error: 0  previewed: 0

  Metadata tagged: 4 files
  Festivals:       Ultra Music Festival Miami (3), Tomorrowland Winter (1)
  Unmatched:       1 (unknown_set_001.mkv)

  Elapsed: 42.0s
```

### Verdict badges

Every file ends with exactly one badge. The badges are padded to a fixed width so the lines
align in a terminal and stay grep-friendly in log files.

| Badge | Meaning for that file |
|-------|-----------------------|
| `done` | Matched a tracklist and embedded fresh chapters and tags |
| `updated` | Already had chapters; re-fetched and wrote newer or missing tags (for example self-healing, or `--regenerate`) |
| `up-to-date` | File already has a stored tracklist and all tags are current; nothing written |
| `skipped` | No confident match (auto mode), user entered `0`, tracklist had fewer than 2 tracks, or file type is not supported |
| `error` | A tool failed (for example `mkvpropedit`) or the tracklist fetch raised. The file is left untouched. |

### Summary panel

The summary at the end of a run shows counts for each verdict plus a total `Elapsed` row.
The `Unmatched` list includes both `skipped` files (with the reason, for example
`low confidence (score 84)`) and `error` files (with the short error), so you can see at a
glance which files still need attention.

### Verbosity and piping

| Mode | Verdict lines | Summary panel | Transient spinner | Extra output |
|------|---------------|---------------|-------------------|--------------|
| default (interactive) | yes | yes | yes | candidate table, selection prompt |
| `--auto` | yes | yes | yes | none (no prompt) |
| `--quiet` / `-q` | no | yes | no | nothing per file |
| `--verbose` / `-v` | yes | yes | no | INFO lines (key decisions, search results, parse info) |
| `--debug` | yes | yes | no | INFO + DEBUG (cache hits, retries, internals) |
| piped to a file (for example `cratedigger identify ... > run.log`) | yes | yes | no | same as interactive otherwise |

The spinner is a convenience for live terminals. Anything that captures or logs the output
(pipes, `--verbose`, `--debug`, `--quiet`) drops the spinner so the captured log stays
clean; the verdict lines and summary are identical in every mode.

The interactive candidate table is unchanged from previous versions. The selection prompt
itself has been tightened so it no longer collides with the next file's output (previously
the `Select` line and the following file could stitch onto one visual line).

## What changes in your files

`identify` modifies only the files it processes. For each matched file:

- Chapter markers are embedded (one per track, with track name and timestamp)
- Album-level metadata tags are written (tracklist source information, artist list, genres)
- Per-chapter metadata tags are written (track title, performer, label, genre, one set per chapter)

No files are created, moved, or copied. The original video stream and audio are untouched.
Only the metadata section of the MKV file changes.

### Location and country tags

CrateDigger records the set's venue or city using two separate tags, in this order of
preference:

1. **A linked source on the tracklist page.** When the 1001Tracklists page links to a
   festival, venue, conference, or radio channel, that source is written to the matching
   tag (`CRATEDIGGER_1001TL_FESTIVAL`, `CRATEDIGGER_1001TL_VENUE`,
   `CRATEDIGGER_1001TL_CONFERENCE`, or `CRATEDIGGER_1001TL_RADIO`). These are the
   authoritative location fields.
2. **A free-text location from the page title.** When no linked location source is
   present, CrateDigger falls back to the plain-text venue and city pulled from the page
   heading, for example "Alexandra Palace London" on a Fred again.. set. This value is
   written to `CRATEDIGGER_1001TL_LOCATION`.

Only one of these paths is used at a time. If the page carries a linked festival, venue,
conference, or radio source, the free-text `CRATEDIGGER_1001TL_LOCATION` is not written.

**Re-identify cleans up stale location data.** If a file was identified earlier, before
1001Tracklists linked a proper source (so it only got the free-text
`CRATEDIGGER_1001TL_LOCATION`), a later re-identify against the updated page clears the
stale `CRATEDIGGER_1001TL_LOCATION` and writes the authoritative tag (for example
`CRATEDIGGER_1001TL_VENUE = "Alexandra Palace"`) instead. You do not need `--regenerate`
for this; the normal re-identify path handles it.

`CRATEDIGGER_1001TL_COUNTRY` is always populated when the page heading carries a
recognised country name, whether a linked source is present or not. Earlier versions only
set the country when no source link existed; now it is extracted unconditionally so
country-derived downstream logic (organize folder layout, NFO country field) has the
same signal regardless of whether the tracklist links a dedicated source.

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

If a file has chapters but is missing some expected per-chapter or album-level tags (for
example, files identified with an older version of CrateDigger), the full tagging pass
runs automatically on the next `identify` run, reusing the stored tracklist URL so your
curated match is preserved. You do not need `--regenerate` for this. CrateDigger detects
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

**Verdict is `skipped` with detail `low confidence (score X)`**

Same cause as above: auto mode was not confident. Re-run without `--auto` to see the
candidate table, or pass `--tracklist` with the right URL.

**Verdict is `skipped (no results)`**

CrateDigger's generated search returned nothing. Try a broader query:

```bash
cratedigger identify recording.mkv --tracklist "Tiesto Miami 2026"
```

If you already know the tracklist, pass the URL or numeric ID directly with `--tracklist`.

**Verdict is `error (mkvpropedit failed)`**

`mkvpropedit` is missing or could not write to the file. Confirm MKVToolNix is installed
and on your PATH (`mkvpropedit --version`), and that the file is writable.

**Verdict is `error (TracklistError: ...)`**

1001Tracklists returned an unexpected response (rate limit, transient 5xx, parse hiccup).
Re-run the command; a single retry usually clears it. If it persists for the same file,
pass `--tracklist` with the URL so the search step is skipped.

**No spinner appears while a file is processing**

The spinner is disabled when output is being captured or when you passed `--quiet`,
`--verbose`, or `--debug`. That is expected. Per-file verdict lines and the summary panel
still print in every mode.

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
  URL, tracklist title and ID, date, genre list, stage, venue, festival, country, free-text
  location, source type, artist names, and DJ artwork URL. These are stored in the
  `CRATEDIGGER_1001TL_*` namespace.

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
