# Kodi Integration

CrateDigger writes Kodi-compatible NFO files and sidecar artwork alongside each MKV. Kodi and Jellyfin both read the same musicvideo NFO format and the same artwork sidecar conventions, so most of this page applies to both. Plex can read these files via agents that support musicvideo NFOs.

This page covers the Kodi-specific parts: enabling the JSON-RPC sync that refreshes your Kodi library after a CrateDigger run, path mapping when CrateDigger and Kodi access the library through different paths, and troubleshooting. For the NFO contents, artwork files, and poster layouts, see [library layout](library-layout.md).

## Enabling Kodi sync

### Always on (config)

Set `enabled` to `true` in the `kodi` section of `~/.cratedigger/config.json`:

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

When enabled, CrateDigger syncs with Kodi at the end of every `organize` or `enrich` run.

### Per run (flag)

Use `--kodi-sync` to sync for a single run without enabling it globally:

```bash
cratedigger enrich ~/Music/Library/ --kodi-sync
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --kodi-sync
```

## Setting up Kodi JSON-RPC

CrateDigger communicates with Kodi via its JSON-RPC HTTP interface. Enable it in Kodi:

1. Open Kodi and go to **Settings** > **Services** > **Control**.
2. Enable **Allow remote control via HTTP**.
3. Set the **Port** (default: 8080).
4. Set a **Username** and **Password**.
5. If CrateDigger runs on a different machine, also enable **Allow remote control from applications on other systems**.

## How the sync works

After the `organize` or `enrich` pipeline completes, CrateDigger checks which files had relevant changes and tells Kodi to refresh only those specific items. Changes that trigger a refresh:

- NFO file created or updated
- Cover art (`{stem}-thumb.jpg`, `{stem}-fanart.jpg`) changed
- Per-video poster (`{stem}-poster.jpg`) generated
- Album poster (`folder.jpg`) changed; when this happens, every video in that folder is refreshed so Kodi picks up the new folder artwork

If nothing changed (for example, a re-enrich run where all artifacts were already up to date), no sync request is sent. Run with `--debug` to confirm whether the sync pathway fired.

## Path mapping

If CrateDigger and Kodi access the same library through different paths (for example, CrateDigger uses a local path while Kodi uses a network share), CrateDigger needs to translate between them.

**Auto-detection (default):** CrateDigger compares the filenames it just changed against Kodi's video index and infers the path prefix pair automatically. This works for most setups without any configuration.

**Manual mapping:** If auto-detection does not work for your setup, configure explicit path prefixes:

```json
{
    "kodi": {
        "enabled": true,
        "host": "192.168.1.100",
        "port": 8080,
        "username": "kodi",
        "password": "your-password",
        "path_mapping": {
            "local": "/home/user/Music/Library/",
            "kodi": "smb://server/music/Library/"
        }
    }
}
```

`local` is the path CrateDigger uses on this machine. `kodi` is the path Kodi uses to reach the same location.

## Environment variables

| Variable | Overrides |
|----------|----------|
| `KODI_HOST` | `kodi.host` |
| `KODI_PORT` | `kodi.port` |
| `KODI_USERNAME` | `kodi.username` |
| `KODI_PASSWORD` | `kodi.password` |

## Jellyfin and Plex

**Jellyfin** reads the same musicvideo NFO spec and artwork sidecars CrateDigger writes. No Jellyfin-specific setup is needed. Point Jellyfin at the library folder and it picks up titles, artists, genres, album grouping, posters, thumbs, and fanart from the sidecar files automatically.

**Plex** can read the same files via musicvideo-compatible agents. Plex does not have an equivalent of the JSON-RPC sync, so run a manual library refresh in Plex after a CrateDigger run.

## Common problems

**"Kodi sync failed: connection refused"**

Kodi is not running, or its web server is not enabled. Verify the JSON-RPC settings in Kodi and check that the host and port in your config match.

**"Kodi sync failed: 401 Unauthorized"**

The username or password is incorrect. Check your Kodi web server credentials against your config.

**Items not updating in Kodi**

The library path in Kodi may not match the path CrateDigger is using. If they differ (for example, one is a network share and one is a local mount), configure `path_mapping` as shown above.

**Sync runs but nothing changes in Kodi**

CrateDigger only refreshes items that had actual changes in that run. If all artifacts were already up to date, no sync request is sent. Use `--regenerate` to force regeneration of artifacts, which will trigger a sync.

## See also

- [Library layout](library-layout.md): NFO contents, sidecar files, poster layouts, and artwork sources
- [Tag reference](tag-reference.md): MKV tags that Kodi and Jellyfin surface alongside NFO data
- [enrich command](commands/enrich.md): the `--kodi-sync` flag and operations that trigger a refresh
- [Configuration](configuration.md): full Kodi config reference
