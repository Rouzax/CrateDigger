# Festival Database

CrateDigger uses a `festivals.json` file to recognize festival names and abbreviations in your filenames and metadata. What you put in this file directly affects how your library is organized and named.

## What this file controls

**Name recognition and folder names.** When CrateDigger sees `AMF` in a filename, it looks it up in the festival database and finds it is `Amsterdam Music Festival`. The canonical name (`AMF`) is what appears in your folder and file names. Without an entry for a festival, CrateDigger can only use whatever text appears literally in the filename.

**Edition detection.** When a filename contains `"Dreamstate SoCal"`, CrateDigger splits it into festival `"Dreamstate"` and edition `"SoCal"`. This powers the `{edition}` field in your folder and filename templates, so edition-specific events get their own folders in nested layouts.

**Poster brand colors.** The `color` field sets the gradient base and accent color used in poster generation when no logo or fanart image is available. Without a color, CrateDigger derives a generic gradient from the metadata.

**Search query expansion.** Short uppercase abbreviations (like `AMF`, `EDC`, `ASOT`) are expanded to their full names when CrateDigger searches 1001Tracklists for a match. This improves match quality without affecting your folder names.

**Festival classification.** Recognized festival names help CrateDigger classify a file as a festival set rather than a concert recording.

## File location

CrateDigger looks for `festivals.json` in two places, checking the library-local location first:

1. `{library}/.cratedigger/festivals.json` (library-specific overrides)
2. `~/.cratedigger/festivals.json` (user-level, applies to all libraries)

If neither file exists, CrateDigger falls back to its built-in festival knowledge.

To get the full example file as a starting point:

=== "Linux / macOS"

    ```bash
    curl -o ~/.cratedigger/festivals.json \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/festivals.example.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/festivals.example.json" `
      -OutFile "$env:USERPROFILE\.cratedigger\festivals.json"
    ```

Or, if you have cloned the repository:

```bash
cp festivals.example.json ~/.cratedigger/festivals.json
```

## Format

Each top-level key is the canonical festival name. This is the name that appears in your folder structure and filenames. The value is an object with optional fields:

```json
{
    "Tomorrowland": {
        "aliases": ["TML", "Tomorrowland Weekend 1", "Tomorrowland Weekend 2"],
        "editions": {
            "Brasil": { "color": "#2A9D8F" },
            "Winter": { "color": "#5B9BD5" }
        },
        "color": "#9B1B5A"
    }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `aliases` | list of strings | Alternative names and abbreviations that resolve to this festival |
| `editions` | object | Regional or seasonal variants (see below) |
| `color` | hex string | Brand color used in gradient poster generation |

If an edition has its own `color`, that edition color takes priority over the festival-level color.

### Editions

Editions represent regional or seasonal variants of a festival. Each edition can have its own aliases and color:

```json
{
    "EDC": {
        "aliases": ["Electric Daisy Carnival"],
        "editions": {
            "Las Vegas": { "aliases": ["EDC Las Vegas"] },
            "Mexico": {},
            "Orlando": {}
        },
        "color": "#ED3895"
    }
}
```

When CrateDigger encounters "EDC Las Vegas" in a filename, it resolves to festival `"EDC"` with edition `"Las Vegas"`. The edition name appears in folder paths and filenames wherever `{edition}` is used in your templates.

### Minimal entries

A festival with no aliases, editions, or color can be an empty object. CrateDigger still recognizes the name during analysis and classification:

```json
{
    "Awakenings": {},
    "Glastonbury": {},
    "Creamfields": {}
}
```

## How matching works

When CrateDigger analyzes a filename or tag, it checks against the festival database in this order:

1. **Exact match** against canonical names
2. **Alias match** (case-insensitive) against all aliases
3. **Edition decomposition:** names like "Dreamstate SoCal" are split into festival "Dreamstate" and edition "SoCal"
4. **Diacritics-insensitive match** handles accented characters

## Alias rules and pitfalls

The canonical name is automatically recognized without needing to be listed as its own alias. CrateDigger adds a self-mapping for every canonical key, so `"EDC"` already resolves to `"EDC"` the moment you add it as a top-level key.

**Do not add a canonical name as an alias for another entry.** If your file has:

```json
{
    "Electric Daisy Carnival": {
        "aliases": ["EDC"]
    }
}
```

...then `"EDC"` will resolve to `"Electric Daisy Carnival"` instead of itself. Any files with `"EDC"` in their name would be named after the full festival name, which may not be what you want. CrateDigger will also log a warning if two entries point at each other.

**Do not list the same name as a canonical key in one entry and as an alias in another.** The second definition silently wins. Choose one entry as the canonical and list all alternative names under its `aliases`.

**Wrong:**
```json
{
    "EDC": {},
    "Electric Daisy Carnival": { "aliases": ["EDC"] }
}
```

**Correct:**
```json
{
    "EDC": { "aliases": ["Electric Daisy Carnival"] }
}
```

## Adding your own festivals

Add new entries by editing your `festivals.json`. For example:

```json
{
    "My Local Festival": {
        "aliases": ["MLF"],
        "color": "#FF6600"
    }
}
```

CrateDigger picks up the new entry on the next run.

## What the example file includes

`festivals.example.json` covers major electronic music festivals including Tomorrowland, Ultra Music Festival, EDC, ASOT, AMF, Dreamstate, and more. It is a good starting point for most libraries. Add your own entries for any festivals it does not cover.

## Related

- [Configuration: artists.json](configuration.md#artist-aliases): artist name aliases and B2B group definitions
- [audit-logos](commands/audit-logos.md): check which festivals in your library have curated poster logos
