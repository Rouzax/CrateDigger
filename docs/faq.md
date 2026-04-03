# FAQ

## MediaInfo not found

**Q: I get an error about MediaInfo not being found. What do I do?**

A: CrateDigger requires MediaInfo to extract metadata from media files. Install it for your platform:

- Ubuntu/Debian: `sudo apt install mediainfo`
- macOS: `brew install media-info`
- Windows: `scoop install mediainfo` or download from [mediaarea.net](https://mediaarea.net/en/MediaInfo/Download)

If MediaInfo is installed but not on your PATH, set the explicit path in your config:

```json
{
    "tool_paths": {
        "mediainfo": "/usr/local/bin/mediainfo"
    }
}
```

## Chapters not embedding

**Q: The identify command finds a tracklist but chapters are not embedded. Why?**

A: Chapter embedding requires `mkvpropedit` from MKVToolNix. Check that:

1. MKVToolNix is installed (`sudo apt install mkvtoolnix` or equivalent)
2. The file is an MKV or WEBM container (MP4 files are not supported for chapter embedding)
3. The tracklist has at least 2 tracks with timing data. Single-track listings are skipped because they provide no navigation value.

If mkvpropedit is installed but not on your PATH, set the path in config:

```json
{
    "tool_paths": {
        "mkvpropedit": "/usr/local/bin/mkvpropedit"
    }
}
```

## Posters not generating

**Q: The enrich command runs but no poster images appear. What is wrong?**

A: Poster generation depends on available background sources. Check the priority chain in your config (`poster_settings`). If no source is available, the gradient fallback is used. If posters are still missing:

1. Make sure Pillow is installed (it is a required dependency)
2. For advanced image processing, install the vision extra: `pip install "cratedigger[vision]"`
3. Run with `--verbose` to see which background sources are tried and why they fail

## Files not being recognized

**Q: CrateDigger skips some of my files. How do I fix this?**

A: CrateDigger only processes files with recognized media extensions. Check the `media_extensions` config section. The defaults include common video formats (.mp4, .mkv, .webm, .avi, .mov, .m2ts, .ts) and audio formats (.mp3, .m4a, .flac, .wav, .aac, .ogg, .opus).

Also check the `skip_patterns` config. Files matching any skip pattern are excluded. The default patterns skip `*/BDMV/*` and `Dolby*`.

## Classification is wrong

**Q: CrateDigger classifies a concert as a festival set, or vice versa. How do I correct it?**

A: Use the `content_type_rules` config section to force classification with glob patterns:

```json
{
    "content_type_rules": {
        "force_concert": [
            "Adele/*",
            "Pink Floyd/*"
        ],
        "force_festival": [
            "*/Ultra/*"
        ]
    }
}
```

Patterns are matched against the relative path from the source root.

## Auto mode skips too many files

**Q: When I run `identify --auto`, most files are skipped. Can I adjust the sensitivity?**

A: Auto mode requires a minimum score of 150 and a minimum gap of 20 between the best and second-best results. These thresholds are designed to avoid false matches. If your files have unusual naming conventions, the search queries may not produce strong matches.

Try these approaches:

1. Run without `--auto` first, to see which tracklists match interactively
2. Use `--tracklist` to provide a direct URL for hard-to-match files
3. Rename files to include the artist name and festival name clearly

## Fanart lookups fail

**Q: Enrich runs but fanart is not downloaded. What is going on?**

A: Fanart lookups require:

1. `fanart.enabled` set to `true` in config (this is the default)
2. A valid API key. A project API key is built in, so this should work out of the box. If you get rate-limited, add your personal API key from [fanart.tv](https://fanart.tv/get-an-api-key/).
3. The artist must exist on MusicBrainz. CrateDigger looks up the MusicBrainz ID to query fanart.tv.

Run with `--verbose` to see the lookup process and any errors.

## Library not recognized

**Q: The enrich command says "not a CrateDigger library". What does that mean?**

A: The enrich command requires a library that was created by the organize command. Organizing creates a `.cratedigger` marker directory at the library root. If you have media files that were not organized by CrateDigger, run organize first:

```bash
cratedigger organize ~/my-files/ --output ~/Music/Library/
```

Then enrich the organized library:

```bash
cratedigger enrich ~/Music/Library/
```
