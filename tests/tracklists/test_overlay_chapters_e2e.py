"""End-to-end coverage for overlay-chapter + mashup-metadata wiring in
cli_handler._fetch_and_embed.

These drive the real glue (anchor build -> overlays.assemble -> trim -> title
strip -> embed_chapters) with a stubbed session and a mocked embed_chapters so
the assembled chapters and the kwargs forwarded to embed_chapters can be
inspected without any mkvpropedit / real I/O.
"""

from unittest.mock import MagicMock, patch

from festival_organizer.tracklists.api import Track, TracklistExport
from festival_organizer.tracklists.cli_handler import _fetch_and_embed
from festival_organizer.tracklists.overlays import merge_chapter_tags


def _make_config(
    *,
    overlay_chapters: bool = True,
    overlay_fold_seconds: int = 20,
    mashup_metadata: bool = True,
    chapter_title_labels: bool = False,
) -> MagicMock:
    cfg = MagicMock()
    cfg.tracklists_settings = {"genre_top_n": 5}
    cfg.resolve_artist = lambda name: name
    cfg.overlay_chapters = overlay_chapters
    cfg.overlay_fold_seconds = overlay_fold_seconds
    cfg.mashup_metadata = mashup_metadata
    cfg.chapter_title_labels = chapter_title_labels
    return cfg


def _make_export() -> TracklistExport:
    """A single-source export exercising every overlay shape.

    Anchors (from export lines, timestamped):
      00:00 plain main "Opener - Intro [LBL0]"
      02:00 plain main "Host - Host Track [LBL1]"

    HTML tracks (carry the structured row data):
      anchor mains at the same start_ms as the lines,
      a timed overlay 5s after the 02:00 host  (folds into host),
      a timed overlay 30s after the host       (breaks out as its own chapter),
      a positionless (cue 0) overlay           (folds into the current anchor),
      a mashup main at 04:00 with two tlpSubTog children (group 7).

    supplement_chapters_from_tracks lifts the mashup main into an anchor.
    """
    lines = [
        "[00:00] Opener - Intro [LBL0]",
        "[02:00] Host - Host Track [LBL1]",
    ]

    opener = Track(
        start_ms=0,
        raw_text="Opener - Intro",  # 1001TL raw_text never carries the [Label]
        artist_slugs=["opener"],
        artist_names=["Opener"],
        title="Intro",
        label="LBL0",
        genres=["House"],
    )
    host = Track(
        start_ms=120_000,
        raw_text="Host - Host Track",
        artist_slugs=["host"],
        artist_names=["Host"],
        title="Host Track",
        label="LBL1",
        genres=["Techno"],
    )
    fold_overlay = Track(
        start_ms=125_000,  # 5s after host -> folds
        raw_text="Folded - Acapella",
        artist_slugs=["folded"],
        artist_names=["Folded"],
        title="Acapella",
        label="LBLF",
        genres=["Vocal"],
        is_overlay=True,
    )
    breakout_overlay = Track(
        start_ms=150_000,  # 30s after host -> breaks out
        raw_text="Breakout - Solo",
        artist_slugs=["breakout"],
        artist_names=["Breakout"],
        title="Solo",
        label="LBLB",
        genres=["Trance"],
        is_overlay=True,
    )
    positionless = Track(
        start_ms=0,  # cue 0 -> folds into current anchor (the opener)
        raw_text="Positionless - Sample",
        artist_slugs=["positionless"],
        artist_names=["Positionless"],
        title="Sample",
        genres=[],
        is_overlay=True,
    )
    mashup_main = Track(
        start_ms=240_000,  # 04:00
        raw_text="A vs. B - Mashup Main",
        artist_slugs=["junk-mega-slug"],
        artist_names=["Junk Mega"],
        title="Mashup Main",
        label="MEGA",
        genres=[],
        is_mashup=True,
        group_id=7,
    )
    sub_a = Track(
        start_ms=0,
        raw_text="Component A - Song A",
        artist_slugs=["component-a"],
        artist_names=["Component A"],
        title="Song A",
        genres=["Bass"],
        is_overlay=True,
        is_subcomponent=True,
        group_id=7,
    )
    sub_b = Track(
        start_ms=0,
        raw_text="Component B - Song B",
        artist_slugs=["component-b"],
        artist_names=["Component B"],
        title="Song B",
        genres=["Dubstep"],
        is_overlay=True,
        is_subcomponent=True,
        group_id=7,
    )

    tracks = [
        opener,
        positionless,
        host,
        fold_overlay,
        breakout_overlay,
        mashup_main,
        sub_a,
        sub_b,
    ]
    return TracklistExport(
        lines=lines,
        url="https://www.1001tracklists.com/tracklist/abc/dj.html",
        title="DJ @ Festival",
        genres=["House"],
        dj_artists=[("dj", "DJ")],
        tracks=tracks,
    )


def _make_session(export: TracklistExport) -> MagicMock:
    sess = MagicMock()
    sess.export_tracklist.return_value = export
    sess._dj_cache = None
    return sess


def _run(config, tmp_path, *, duration_seconds=600.0):
    export = _make_export()
    session = _make_session(export)
    captured: dict = {}

    def fake_embed(filepath, chapters, **kwargs):
        captured["chapters"] = chapters
        captured["assembled"] = kwargs.get("assembled")
        captured["mashup_metadata"] = kwargs.get("mashup_metadata")
        captured["tracks"] = kwargs.get("tracks")
        return True

    fake_mkv = tmp_path / "dj.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch(
            "festival_organizer.tracklists.cli_handler.embed_chapters",
            side_effect=fake_embed,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_existing_chapters",
            return_value=None,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.chapters_are_identical",
            return_value=False,
        ),
    ):
        status, vstatus, _ = _fetch_and_embed(
            session,
            export.url,
            fake_mkv,
            config,
            preview=False,
            quiet=True,
            language="eng",
            duration_seconds=duration_seconds,
            youtube_id="",
        )
    captured["status"] = status
    captured["vstatus"] = vstatus
    return captured


def test_overlays_enabled_folds_breaks_out_and_merges_mashup(tmp_path):
    """overlay_chapters=True, fold=20: fold + breakout shape, mashup merge."""
    cfg = _make_config(overlay_chapters=True, overlay_fold_seconds=20)
    captured = _run(cfg, tmp_path)

    assert captured["status"] == "updated"
    chapters = captured["chapters"]
    titles = [c.title for c in chapters]

    # Opener (00:00) with positionless folded -> "Opener vs. Positionless - ...";
    # Host (02:00) with the 5s overlay folded; the 30s overlay breaks out as its
    # own chapter; the 04:00 mashup main is its own chapter.
    # Expected 4 chapters: opener, host(folded), breakout, mashup.
    assert len(chapters) == 4

    # Opener folds the positionless overlay.
    assert titles[0].startswith("Opener vs. Positionless")
    # Host folds the 5s overlay.
    assert "Host" in titles[1] and "Folded" in titles[1]
    # Breakout is its own chapter (30s after host).
    assert "Breakout" in titles[2]
    assert chapters[2].timestamp.startswith("00:02:30")
    # Mashup chapter present.
    assert chapters[3].timestamp.startswith("00:04:00")

    # mashup_metadata forwarded and assembled list aligns 1:1 with chapters.
    assert captured["mashup_metadata"] is True
    assembled = captured["assembled"]
    assert assembled is not None
    assert len(assembled) == len(chapters)

    # The mashup chapter's merged per-chapter tags carry the component artists,
    # not the junk mega-slug.
    mashup_ac = assembled[3]
    tags = merge_chapter_tags(
        mashup_ac.primary, mashup_ac.contributors, mashup_metadata=True
    )
    slugs = tags["CRATEDIGGER_TRACK_PERFORMER_SLUGS"].split("|")
    names = tags["CRATEDIGGER_TRACK_PERFORMER_NAMES"].split("|")
    assert "component-a" in slugs and "component-b" in slugs
    assert "junk-mega-slug" not in slugs
    assert len(slugs) == len(names)
    assert set(tags["CRATEDIGGER_TRACK_GENRE"].split("|")) == {"Bass", "Dubstep"}


def test_overlays_disabled_anchor_count_but_mashup_still_merges(tmp_path):
    """overlay_chapters=False: no breakouts, anchor count only, but a mashup
    chapter still gets merged metadata when mashup_metadata=True."""
    cfg = _make_config(overlay_chapters=False, mashup_metadata=True)
    captured = _run(cfg, tmp_path)

    assert captured["status"] == "updated"
    chapters = captured["chapters"]
    # Anchors only: opener (00:00), host (02:00), mashup (04:00). No breakout.
    assert len(chapters) == 3
    assert all("Breakout" not in c.title for c in chapters)

    # Mashup still merges component metadata via tlpSubTog children.
    assembled = captured["assembled"]
    mashup_ac = assembled[2]
    tags = merge_chapter_tags(
        mashup_ac.primary, mashup_ac.contributors, mashup_metadata=True
    )
    slugs = tags["CRATEDIGGER_TRACK_PERFORMER_SLUGS"].split("|")
    assert "component-a" in slugs and "component-b" in slugs
    assert "junk-mega-slug" not in slugs


def test_chapter_title_labels_default_strips_brackets(tmp_path):
    """chapter_title_labels=False (default): no chapter title keeps a trailing
    [Label] bracket."""
    cfg = _make_config(chapter_title_labels=False)
    captured = _run(cfg, tmp_path)
    titles = [c.title for c in captured["chapters"]]
    assert titles, "expected chapters"
    for t in titles:
        assert not t.rstrip().endswith("]"), f"label not stripped: {t!r}"


def test_chapter_title_labels_true_retains_brackets(tmp_path):
    """chapter_title_labels=True: titles retain the [Label] bracket."""
    cfg = _make_config(chapter_title_labels=True)
    captured = _run(cfg, tmp_path)
    titles = [c.title for c in captured["chapters"]]
    # The opener anchor carried [LBL0]; with labels on it must survive.
    assert any("[" in t and t.rstrip().endswith("]") for t in titles)


def test_idempotent_second_run_is_up_to_date(tmp_path):
    """Embed once, then re-run with the embedded chapters/stored URL present:
    the second run reports up_to_date with no churn."""
    cfg = _make_config()
    first = _run(cfg, tmp_path)
    assert first["status"] == "updated"
    embedded = first["chapters"]

    # Second run: the file now carries the new-format chapters and a stored URL,
    # and all per-chapter / album tags are present, so it must settle.
    export = _make_export()
    session = _make_session(export)
    fake_mkv = tmp_path / "dj.mkv"

    stored = {
        "url": export.url,
        "title": export.title,
        "id": "",
        "youtube_id": "",
        "date": "",
        "genres": "House",
        "dj_artwork": "",
        "stage": "",
        "venue": "",
        "festival": "",
        "conference": "",
        "radio": "",
        "artists": "DJ",
        "country": "",
        "location": "",
        "source_type": "",
        "albumartist_slugs": "dj",
        "albumartist_display": "DJ",
    }

    with (
        patch(
            "festival_organizer.tracklists.cli_handler.extract_existing_chapters",
            return_value=embedded,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_stored_tracklist_info",
            return_value=stored,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_chapter_tags",
            return_value=True,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_album_artist_display_tags",
            return_value=True,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_legacy_chapter_title",
            return_value=False,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.chapter_tags_need_refresh",
            return_value=False,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.build_1001tl_tags",
            return_value={},
        ),
    ):
        status, vstatus, _ = _fetch_and_embed(
            session,
            export.url,
            fake_mkv,
            cfg,
            preview=False,
            quiet=True,
            language="eng",
            duration_seconds=600.0,
            youtube_id="",
        )

    assert (status, vstatus) == ("up_to_date", "up-to-date")


def test_stale_per_chapter_tags_self_heal_without_regenerate(tmp_path):
    """When the embedded chapters match but the per-chapter tag derivation drifted
    (chapter_tags_need_refresh -> True), identify re-embeds on a plain run and
    reports updated with the stale-tags reason. No --regenerate required."""
    cfg = _make_config()
    first = _run(cfg, tmp_path)
    embedded = first["chapters"]

    export = _make_export()
    session = _make_session(export)
    fake_mkv = tmp_path / "dj.mkv"

    stored = {"url": export.url, "title": export.title, "id": "", "youtube_id": ""}

    def fake_embed(filepath, chapters, **kwargs):
        return True

    with (
        patch(
            "festival_organizer.tracklists.cli_handler.embed_chapters",
            side_effect=fake_embed,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_existing_chapters",
            return_value=embedded,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_stored_tracklist_info",
            return_value=stored,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_chapter_tags",
            return_value=True,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_album_artist_display_tags",
            return_value=True,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.has_legacy_chapter_title",
            return_value=False,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.chapter_tags_need_refresh",
            return_value=True,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.build_1001tl_tags",
            return_value={},
        ),
    ):
        status, vstatus, reason = _fetch_and_embed(
            session,
            export.url,
            fake_mkv,
            cfg,
            preview=True,  # preview short-circuits before the real embed write
            quiet=True,
            language="eng",
            duration_seconds=600.0,
            youtube_id="",
        )

    assert status == "updated"
    assert "refreshed stale per-chapter tags" in reason
