# Kodi Integration

CrateDigger writes media-server-compatible metadata: Kodi-style NFO files alongside each MKV plus sidecar artwork. Kodi and Jellyfin both read the same musicvideo NFO spec and the same artwork sidecar conventions, so everything on this page applies to both. Plex can read these files via agents that support musicvideo NFOs.

This page covers the Kodi-specific parts: enabling the JSON-RPC sync that refreshes the Kodi library after a CrateDigger run, path mapping when CrateDigger and Kodi access the library through different paths, and environment overrides. For the NFO contents, poster/thumb/fanart files, and their sources, see [library layout](library-layout.md).

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

The enrich/organize header box shows a `Kodi sync: yes (flag)` or `yes (config)` row when either trigger is active, so you can tell at a glance whether the sync will run.

## Setting up Kodi JSON-RPC

CrateDigger communicates with Kodi via its JSON-RPC HTTP interface. You need to enable the web server in Kodi:

1. Open Kodi and go to **Settings** > **Services** > **Control**.
2. Enable **Allow remote control via HTTP**.
3. Set a **Port** (default: 8080).
4. Set a **Username** and **Password**.
5. Optionally enable **Allow remote control from applications on other systems** if CrateDigger runs on a different machine.

## How it works

After the organize or enrich pipeline completes, CrateDigger checks which files had relevant changes (NFO updates, artwork changes, poster generation, fanart downloads). It then tells Kodi to refresh only those specific items rather than triggering a full library scan.

Relevant operations that trigger a Kodi refresh:

- NFO file creation or update (the `nfo` op)
- Cover art changes (the `art` op)
- Per-video poster generation (the `posters` op)
- Album poster generation — when `folder.jpg` changes, every video in that folder is refreshed so Kodi picks up the new folder artwork

Under `--debug`, CrateDigger logs `Kodi sync: no kodi-affecting changes` when a run produces nothing to refresh (for example, an idempotent re-enrich on a fully-enriched library) so you can confirm the sync pathway ran.

See [library layout](library-layout.md) for what each of those files contains and where the data comes from.

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

## Jellyfin and Plex

Jellyfin reads the same musicvideo NFO spec and artwork sidecars CrateDigger writes; no Jellyfin-specific setup is needed. Point Jellyfin at the library and it picks up titles, artists, genres, album grouping, posters, thumbs, and fanart from the sidecar files.

Plex can read the same files through agents that support musicvideo NFOs. Plex does not have an equivalent of the JSON-RPC sync hook, so run a manual library refresh in Plex after a CrateDigger run.

## Troubleshooting

**"Kodi sync failed: connection refused"**
: Verify that Kodi is running and the web server is enabled. Check the host and port in your config.

**"Kodi sync failed: 401 Unauthorized"**
: The username or password is incorrect. Check your Kodi web server credentials.

**Items not updating in Kodi**
: Make sure the library path in Kodi matches the output path used by CrateDigger. If paths differ, configure `path_mapping`.

**Sync runs but nothing changes in Kodi**
: CrateDigger only refreshes items that had actual changes. If all artifacts were already up to date (skipped), no sync is triggered. Run with `--debug` to confirm the sync pathway fired; use `--regenerate` to force regeneration.

## See also

- [Library layout](library-layout.md) — NFO contents, sidecar files, poster layouts, artwork sources. What Kodi/Jellyfin actually read.
- [Tag reference](tag-reference.md) — tags inside the MKV that Kodi and Jellyfin surface alongside NFO data.
- [Enrich command](commands/enrich.md) — the `--kodi-sync` flag and operations that trigger refresh.
