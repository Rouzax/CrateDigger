# Kodi Integration

CrateDigger can automatically notify Kodi to refresh library items after enrichment or organization. This keeps your Kodi library in sync without manual rescans.

## Enabling Kodi sync

### In config

Set `enabled` to `true` in the `kodi` section of your config:

```json
{
    "kodi": {
        "enabled": true,
        "host": "192.168.1.100",
        "port": 8080,
        "username": "kodi",
        "password": "your-password"
    }
}
```

When enabled, CrateDigger syncs with Kodi automatically after every organize or enrich run.

### Per-command

Use the `--kodi-sync` flag to trigger sync for a single run, without enabling it globally:

```bash
cratedigger enrich ~/Music/Library/ --kodi-sync
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --kodi-sync
```

## Setting up Kodi JSON-RPC

CrateDigger communicates with Kodi via its JSON-RPC HTTP interface. You need to enable the web server in Kodi:

1. Open Kodi and go to **Settings** > **Services** > **Control**
2. Enable **Allow remote control via HTTP**
3. Set a **Port** (default: 8080)
4. Set a **Username** and **Password**
5. Optionally enable **Allow remote control from applications on other systems** if CrateDigger runs on a different machine

## How it works

After the organize or enrich pipeline completes, CrateDigger checks which files had relevant changes (NFO updates, artwork changes, poster generation, fanart downloads). It then tells Kodi to refresh only those specific items rather than triggering a full library scan.

Relevant operations that trigger a Kodi refresh:

- NFO file creation or update
- Cover art changes
- Poster generation
- Album poster (folder.jpg) generation
- Fanart downloads

## NFO files and Kodi

CrateDigger generates Kodi-compatible NFO files during enrichment. These XML files contain metadata that Kodi reads when adding items to its library:

- Title, artist, year
- Genre (configurable via `nfo_settings`)
- Plot/description

Kodi automatically picks up NFO files when they are placed alongside media files with a matching name.

## Path mapping

When CrateDigger and Kodi access the same library through different paths (e.g., CrateDigger uses a local path while Kodi uses a network share), path mapping translates between them.

CrateDigger attempts to auto-detect path mappings from the Kodi library. If auto-detection does not work for your setup, you can configure explicit mappings in the `kodi` config section:

```json
{
    "kodi": {
        "enabled": true,
        "host": "192.168.1.100",
        "port": 8080,
        "username": "kodi",
        "password": "your-password",
        "path_mapping": {
            "/home/user/Music/Library/": "smb://server/music/Library/"
        }
    }
}
```

## Environment variables

All Kodi settings can be overridden with environment variables:

| Variable | Description |
|----------|-------------|
| `KODI_HOST` | Kodi hostname or IP |
| `KODI_PORT` | Kodi HTTP port |
| `KODI_USERNAME` | Kodi web server username |
| `KODI_PASSWORD` | Kodi web server password |

## Troubleshooting

**"Kodi sync failed: connection refused"**
: Verify that Kodi is running and the web server is enabled. Check the host and port in your config.

**"Kodi sync failed: 401 Unauthorized"**
: The username or password is incorrect. Check your Kodi web server credentials.

**Items not updating in Kodi**
: Make sure the library path in Kodi matches the output path used by CrateDigger. If paths differ, configure `path_mapping`.

**Sync runs but nothing changes in Kodi**
: CrateDigger only refreshes items that had actual changes. If all artifacts were already up to date (skipped), no sync is triggered. Use `--regenerate` to force regeneration.
