# Festival Database

CrateDigger uses a festival configuration file to recognize festival names, resolve aliases, handle regional editions, and assign brand colors for poster generation.

## File location

The festival database is stored in `festivals.json`. CrateDigger looks for it in:

1. `<library>/.cratedigger/festivals.json` (library-specific)
2. `~/.cratedigger/festivals.json` (user-level)

Copy the example file to get started:

```bash
cp festivals.example.json ~/.cratedigger/festivals.json
```

## Format

Each top-level key is the canonical festival name. The value is an object with optional fields:

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
| `aliases` | list of strings | Alternative names that resolve to this festival |
| `editions` | object | Regional or seasonal editions |
| `color` | string | Hex color code for poster generation |

### Editions

Editions represent regional or seasonal variants of a festival. Each edition can have its own aliases and color:

```json
{
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

When a file contains "EDC Las Vegas" or "Electric Daisy Carnival Las Vegas", CrateDigger resolves it to the canonical festival "EDC" with edition "Las Vegas".

### Minimal entries

A festival with no aliases, editions, or color can be an empty object:

```json
{
    "Awakenings": {},
    "Glastonbury": {},
    "Creamfields": {}
}
```

These entries still allow CrateDigger to recognize the name during classification.

## How festivals are matched

During file analysis and classification, CrateDigger checks filenames and metadata against the festival database:

1. **Exact match** against canonical names
2. **Alias match** (case-insensitive) against all aliases
3. **Edition decomposition** splits names like "Dreamstate SoCal" into festival "Dreamstate" + edition "SoCal"
4. **Diacritics-insensitive matching** handles accented characters

The canonical name is used in folder paths and filenames. The edition appears when the template includes `{edition}` or `{ edition}`.

## Adding custom festivals

Add new festivals by editing your `festivals.json`:

```json
{
    "My Local Festival": {
        "aliases": ["MLF"],
        "color": "#FF6600"
    }
}
```

After adding a festival, CrateDigger will recognize it during classification and use the canonical name for organization.

## Example file

The included `festivals.example.json` covers major electronic music festivals worldwide, including Tomorrowland, Ultra Music Festival, EDC, ASOT, AMF, Dreamstate, and many more. Use it as a starting point and customize to match your collection.
