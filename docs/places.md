# Places

CrateDigger uses a `places.json` file to recognise named, branded entities that host DJ sets. What you put in this file directly affects how your library is organised and named.

## What counts as a place?

A "place" in CrateDigger is any named entity that a DJ set is associated with, other than the artist performing it. That includes:

- **Recurring festivals** such as Tomorrowland, EDC, or Coachella.
- **Permanent clubs** such as Printworks (London) or Fabric.
- **One-off event venues** such as Alexandra Palace.
- **Venue brands** such as Hï Ibiza or Ushuaïa Ibiza, where multiple physical locations share a brand identity.

All of these live in the same `places.json` file and use the same schema. There is no structural difference between a festival entry and a venue entry.

## What this file controls

**Name recognition and folder names.** When CrateDigger sees `AMF` in a filename, it looks it up in the places database and finds it is `Amsterdam Music Festival`. The canonical name (`AMF`) is what appears in your folder and file names. Without an entry for a place, CrateDigger can only use whatever text appears literally in the filename or metadata.

**Edition detection.** When a filename contains `"Dreamstate SoCal"`, CrateDigger splits it into place `"Dreamstate"` and edition `"SoCal"`. This powers the `{edition}` field in your folder and filename templates, so edition-specific events get their own folders in nested layouts. See [Editions](#editions) below for when editions apply and when they do not.

**Poster brand colors.** The `color` field sets the gradient base and accent color used in poster generation when no logo or fanart image is available. Without a color, CrateDigger derives a generic gradient from the metadata.

**Search query expansion.** Short uppercase abbreviations (like `AMF`, `EDC`, `ASOT`) are expanded to their full names when CrateDigger searches 1001Tracklists for a match. This improves match quality without affecting your folder names.

**Venue and location routing.** When a set has no linked festival on 1001Tracklists, CrateDigger looks for a linked venue or a plain-text location instead. If the venue or location matches an entry in `places.json`, the set routes by the canonical place name. If not, CrateDigger uses the raw text. Adding a `places.json` entry for a venue is all it takes to get clean canonical folder names for that venue.

## File location

CrateDigger looks for `places.json` in two places, checking the library-local location first:

1. `{library}/.cratedigger/places.json` (library-specific overrides, travels with the library)
2. User-level, applies to all libraries:

| Platform | Path |
|----------|------|
| Linux | `~/CrateDigger/places.json` |
| Windows | `Documents\CrateDigger\places.json` |

If neither file exists, CrateDigger falls back to its built-in place knowledge.

To get the full example file as a starting point, download it to your user-level location:

=== "Linux"

    ```bash
    curl -o ~/CrateDigger/places.json \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/places.example.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/places.example.json" `
      -OutFile "$env:USERPROFILE\Documents\CrateDigger\places.json"
    ```

Or, if you have cloned the repository:

=== "Linux"

    ```bash
    cp places.example.json ~/CrateDigger/places.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Copy-Item places.example.json "$env:USERPROFILE\Documents\CrateDigger\places.json"
    ```

## Format

Each top-level key is the canonical place name. This is the name that appears in your folder structure and filenames. The value is an object with optional fields:

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
| `aliases` | list of strings | Alternative names and abbreviations that resolve to this place |
| `editions` | object | Spin-off variants (regional, seasonal); see below |
| `color` | hex string | Brand color used in gradient poster generation |

If an edition has its own `color`, that edition color takes priority over the place-level color.

### Editions

Editions represent distinct spin-off variants of a place, not individual yearly instances. A festival's annual edition in the same country is the same festival; Tomorrowland Brasil is a genuinely separate event with its own look and feel. Use the `editions` block for that kind of split.

Real examples from `places.example.json`:

```json
{
    "Tomorrowland": {
        "aliases": ["TML", "Tomorrowland Weekend 1", "Tomorrowland Weekend 2"],
        "editions": {
            "Brasil": { "color": "#2A9D8F" },
            "Winter": { "color": "#5B9BD5" }
        },
        "color": "#9B1B5A"
    },
    "EDC": {
        "aliases": ["Electric Daisy Carnival"],
        "editions": {
            "Las Vegas": { "aliases": ["EDC Las Vegas"] },
            "Mexico": {},
            "Orlando": {},
            "Thailand": {}
        },
        "color": "#ED3895"
    }
}
```

When CrateDigger encounters "EDC Las Vegas" in a filename, it resolves to place `"EDC"` with edition `"Las Vegas"`. The edition name appears in folder paths and filenames wherever `{edition}` is used in your templates.

**Do not create an edition for each year.** The year is always tracked separately via the `{year}` token. An entry like `"editions": { "2023": {}, "2024": {} }` creates an unnecessary folder level and defeats the purpose of the field.

### Venues and the editions block

For most venues, no `editions` block is needed. A standalone entry with aliases and a color is all you need:

```json
{
    "Printworks": {
        "color": "#1A1A1A"
    },
    "Alexandra Palace": {
        "aliases": ["Alexandra Palace London", "Ally Pally"]
    }
}
```

When a venue brand has genuinely distinct physical locations with their own identity, you can model them in two ways. The choice is yours as curator.

**Option A: siblings** (each location is its own top-level entry):

```json
{
    "Hï Ibiza": {
        "color": "#D4A017"
    },
    "Ushuaïa Ibiza": {
        "color": "#00A3CC"
    }
}
```

**Option B: editions of a shared parent** (useful if you want all sets from this brand under one canonical name):

```json
{
    "Ibiza Group": {
        "editions": {
            "Hï Ibiza": {},
            "Ushuaïa Ibiza": {}
        }
    }
}
```

With Option B, a set recorded at Hï Ibiza would produce a folder named `Ibiza Group Hï Ibiza` in a flat layout, or `Ibiza Group Hï Ibiza/{year}/{artist}` in a nested layout. With Option A, you get `Hï Ibiza/{year}/{artist}`. Neither is wrong; choose whichever fits how you want to browse your library.

### Minimal entries

A place with no aliases, editions, or color can be an empty object. CrateDigger still recognises the name during analysis and routing:

```json
{
    "Awakenings": {},
    "Glastonbury": {},
    "Creamfields": {}
}
```

## How matching works

When CrateDigger analyses a filename or tag, it checks against the places database in this order:

1. **Exact match** against canonical names
2. **Alias match** (case-insensitive) against all aliases
3. **Edition decomposition:** names like "Dreamstate SoCal" are split into place "Dreamstate" and edition "SoCal"
4. **Diacritics-insensitive match** handles accented characters

If no festival is present on 1001Tracklists, CrateDigger then tries the linked venue, then a plain-text location from the page heading, and finally falls back to the artist name. Adding a place entry for a venue brings it into the same alias-resolution pipeline as festivals.

## Alias rules and pitfalls

The canonical name is automatically recognised without needing to be listed as its own alias. CrateDigger adds a self-mapping for every canonical key, so `"EDC"` already resolves to `"EDC"` the moment you add it as a top-level key.

**Do not add a canonical name as an alias for another entry.** If your file has:

```json
{
    "Electric Daisy Carnival": {
        "aliases": ["EDC"]
    }
}
```

...then `"EDC"` will resolve to `"Electric Daisy Carnival"` instead of itself. Any files with `"EDC"` in their name would be named after the full name, which may not be what you want. CrateDigger will also log a warning if two entries point at each other.

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

## Adding your own entries

Add new entries by editing your `places.json`. You can add festivals, clubs, venues, or any other named entity that hosts sets in your library. For example:

```json
{
    "Printworks": {
        "aliases": ["Printworks London"],
        "color": "#1A1A1A"
    },
    "My Local Festival": {
        "aliases": ["MLF"],
        "color": "#FF6600"
    }
}
```

CrateDigger picks up new entries on the next run.

## What the example file includes

`places.example.json` covers major electronic music festivals including Tomorrowland, Ultra Music Festival, EDC, ASOT, AMF, Dreamstate, and more. It is a good starting point for most libraries. Add your own entries for any festivals, venues, or clubs it does not cover.

## Curated assets: logos and artwork

CrateDigger looks for logo and background artwork in a per-place directory inside your library:

```
{library}/.cratedigger/places/<canonical-name>/logo.png
{library}/.cratedigger/places/<canonical-name>/<edition>/logo.png
```

Where `<canonical-name>` is the top-level key from `places.json` (for example, `Tomorrowland` or `Printworks`) and `<edition>` is the edition name when applicable (for example, `Winter` or `Las Vegas`).

Place the logo file in the matching directory, and CrateDigger will use it instead of generating a gradient poster. Run [`audit-logos`](commands/audit-logos.md) to see which entries in your library have curated logos and which do not.

## Backward compatibility: existing `festivals.json` files

If you have an existing `festivals.json`, you do not need to do anything for 0.15.0. The system reads `festivals.json` when `places.json` is absent, and logs a single deprecation notice per process to tell you the new filename. Your festival entries continue to work exactly as before.

When you are ready to migrate, rename the file:

```bash
mv ~/.cratedigger/festivals.json ~/.cratedigger/places.json
# or for a library-local file:
mv {library}/.cratedigger/festivals.json {library}/.cratedigger/places.json
```

### Deprecated names that still work until 1.0.0

| What | Old (deprecated) | New |
|------|-----------------|-----|
| Config file | `festivals.json` | `places.json` |
| Template token | `{festival}` | `{place}` |
| Layout names | `festival_flat`, `festival_nested` | `place_flat`, `place_nested` |
| Settings key (poster) | `festival_background_priority` | `place_background_priority` |
| Fallback value key | `unknown_festival` | `unknown_place` |
| Curated assets directory | `.cratedigger/festivals/<name>/` | `.cratedigger/places/<name>/` |

Each deprecated name logs a one-shot warning the first time it is used in a process. If you run `cratedigger --check`, any triggered deprecations appear in the output so you can find them without scanning logs manually.

## Related

- [Configuration: artists.json](configuration.md#artist-aliases): artist name aliases and B2B group definitions
- [audit-logos](commands/audit-logos.md): check which places in your library have curated poster logos
