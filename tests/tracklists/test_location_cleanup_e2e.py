"""Cross-layer tests for the CRATEDIGGER_1001TL_LOCATION cleanup contract.

These tests exercise the full ``export_tracklist`` to ``embed_chapters``
pipeline with only the HTTP boundary (``_request``) and the MKV write
boundary (``write_merged_tags`` + ``mkvpropedit``) mocked. Everything in
between (h1 parsing, source cache lookup, ``sources_by_type`` grouping,
location suppression, and the ``embed_chapters`` clear-path logic) runs
for real.

The scenario covered: a file previously enriched with
``CRATEDIGGER_1001TL_LOCATION`` set (free-text venue string derived from
the h1 tail) is re-identified against a tracklist page that now carries
a linked ``Event Location`` source. The stale LOCATION tag must be
cleared on re-embed, not left behind alongside the new
``CRATEDIGGER_1001TL_VENUE`` value.

The unit-level counterpart lives in
``tests/tracklists/test_embed_chapters_orchestration.py`` where
``sources_by_type`` is passed directly into ``embed_chapters``. These
tests close the gap by ensuring the real parse-and-group chain produces
the same input.
"""
from unittest.mock import MagicMock, patch

from festival_organizer.mkv_tags import CLEAR_TAG
from festival_organizer.tracklists.api import TracklistSession
from festival_organizer.tracklists.chapters import (
    embed_chapters, parse_tracklist_lines,
)


def _build_minimal_page_html(h1_inner: str) -> str:
    """Minimal HTML document the exporter can parse: it only needs
    <title> and <h1>."""
    return (
        "<html><head><title>Fred again.. @ Alexandra Palace | 1001Tracklists</title>"
        "</head><body>"
        f'<h1 class="notranslate">{h1_inner}</h1>'
        "</body></html>"
    )


class _StubSourceCache:
    """Minimal source cache double: pre-seeded with per-id type entries.

    Mirrors the subset of the SourceCache API that export_tracklist calls:
    ``get`` (to check freshness), ``put`` (to write after fetch), and
    ``group_by_type`` (to produce the sources_by_type map). The real
    cache does a freshness check on ``get``; for tests we treat every
    seeded entry as fresh.
    """

    def __init__(self, entries: dict[str, dict]):
        self._data = dict(entries)

    def get(self, sid: str):
        return self._data.get(sid)

    def put(self, sid: str, entry: dict) -> None:
        self._data[sid] = entry

    def group_by_type(self, source_ids: list[str]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for sid in source_ids:
            entry = self._data.get(sid)
            if entry:
                groups.setdefault(entry["type"], []).append(entry["name"])
        return groups


def _build_export_mock_responses(page_html: str):
    """Return a _request side_effect that plays back a page GET then an
    AJAX export POST with a tiny but valid tracklist payload."""
    page_resp = MagicMock()
    page_resp.text = page_html
    page_resp.url = (
        "https://www.1001tracklists.com/tracklist/abc123/"
        "fred-again-alexandra-palace-2026.html"
    )

    ajax_resp = MagicMock()
    ajax_resp.json.return_value = {
        "success": True,
        "data": "[00:00] Opener\n[01:00] Second\n[02:00] Third\n",
    }

    responses = [page_resp, ajax_resp]
    calls = {"i": 0}

    def _side_effect(method, url, *args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        if i < len(responses):
            return responses[i]
        extra = MagicMock()
        extra.text = ""
        extra.json.return_value = {"success": False, "message": "unexpected"}
        return extra

    return _side_effect


def test_reidentify_clears_stale_location_when_linked_event_location_appears(tmp_path):
    """End-to-end cleanup: a file that previously carried
    CRATEDIGGER_1001TL_LOCATION = "Alexandra Palace London" is
    re-identified against a tracklist page whose h1 now links a
    /source/ of type "Event Location". The full pipeline (real
    export_tracklist -> real parse_tracklist_lines -> real
    embed_chapters) must emit a TTV=70 tag map that:

      - sets CRATEDIGGER_1001TL_VENUE from the linked Event Location, and
      - clears CRATEDIGGER_1001TL_LOCATION via the CLEAR_TAG sentinel.

    No fixture MKV or mkvpropedit invocation is needed: we patch
    write_merged_tags to capture its arguments and MKVPROPEDIT_PATH so
    the chapter-XML subprocess is a no-op.
    """
    # Page HTML with a linked Event Location source. Suppression upstream
    # (in export_tracklist) will blank export.location because the source
    # is location-bearing; the cleanup itself happens inside embed_chapters
    # when it sees VENUE in the resulting tags.
    h1_inner = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/venue/alexandra-palace/index.html">Alexandra Palace</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    page_html = _build_minimal_page_html(h1_inner)

    cache = _StubSourceCache({
        "venue": {"name": "Alexandra Palace", "type": "Event Location",
                  "country": "United Kingdom"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)), \
         patch.object(session, "_fetch_dj_profile",
                      return_value={"artwork_url": ""}):
        export = session.export_tracklist("abc123")

    # Sanity check the export-layer contract these tests are built on:
    # the h1 location is suppressed when a linked Event Location is present,
    # and sources_by_type carries the venue.
    assert export.location == ""
    assert export.sources_by_type.get("Event Location") == ["Alexandra Palace"]

    chapters = parse_tracklist_lines(export.lines)
    assert len(chapters) >= 2

    fake_mkv = tmp_path / "fred-again-alexandra-palace.mkv"
    fake_mkv.write_bytes(b"")

    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write, \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters,
            tracklist_url=export.url,
            tracklist_title=export.title,
            sources_by_type=export.sources_by_type,
            country=export.country,
            location=export.location,
            tracks=export.tracks,
        )

    # write_merged_tags is called with tags keyed by target-type value; 70
    # is the album-level map.
    album_tags = mock_write.call_args[0][1][70]
    assert album_tags["CRATEDIGGER_1001TL_VENUE"] == "Alexandra Palace"
    assert album_tags["CRATEDIGGER_1001TL_LOCATION"] is CLEAR_TAG


def test_reidentify_writes_location_when_no_linked_location_source(tmp_path):
    """Companion to the cleanup case: when the page's only linked source
    is NOT location-bearing (e.g. an Event Promoter like USB002), the h1
    tail's free-text venue string survives and is written to
    CRATEDIGGER_1001TL_LOCATION. The full pipeline is exercised; no
    mocks between export_tracklist and embed_chapters.
    """
    h1_inner = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/usb002/index.html">USB002</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    page_html = _build_minimal_page_html(h1_inner)

    # Event Promoter is NOT in LOCATION_BEARING_TYPES, so export.location
    # must survive and flow through to the tag map.
    cache = _StubSourceCache({
        "abc": {"name": "USB002", "type": "Event Promoter",
                "country": "United Kingdom"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)), \
         patch.object(session, "_fetch_dj_profile",
                      return_value={"artwork_url": ""}):
        export = session.export_tracklist("abc123")

    assert export.location == "Alexandra Palace London"
    # Country is now extracted from the h1 tail even when a linked source
    # is present: previously this only populated when no source link
    # existed at all.
    assert export.country == "United Kingdom"

    chapters = parse_tracklist_lines(export.lines)
    assert len(chapters) >= 2

    fake_mkv = tmp_path / "fred-again-usb002.mkv"
    fake_mkv.write_bytes(b"")

    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write, \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters,
            tracklist_url=export.url,
            tracklist_title=export.title,
            sources_by_type=export.sources_by_type,
            country=export.country,
            location=export.location,
            tracks=export.tracks,
        )

    album_tags = mock_write.call_args[0][1][70]
    assert album_tags["CRATEDIGGER_1001TL_LOCATION"] == "Alexandra Palace London"
    assert album_tags["CRATEDIGGER_1001TL_COUNTRY"] == "United Kingdom"
    # No venue / festival / conference / radio got written, so the clear
    # path must NOT have fired.
    assert "CRATEDIGGER_1001TL_VENUE" not in album_tags
