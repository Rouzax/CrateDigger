from pathlib import Path

from festival_organizer.notify.models import (
    EmailSet,
    UpdateInfo,
    RunReport,
    RenderedEmail,
    SMTPSettings,
)


def test_email_set_defaults():
    s = EmailSet(
        artist="Eric Prydz",
        event="UMF Miami",
        year="2026",
        note="Resistance",
        genres=["Techno"],
        metric="19 tracks",
        poster_path=Path("/x-poster.jpg"),
        kind="festival_set",
    )
    assert s.artist == "Eric Prydz"
    assert s.genres == ["Techno"]


def test_run_report_groups_and_update():
    report = RunReport(
        channel="new_sets",
        sets=[],
        update=UpdateInfo(installed="0.19.9", latest="0.20.0", behind=True),
        stats={"added": 1, "up_to_date": 2, "errors": 0},
        timestamp="11 Jun 2026, 22:14",
    )
    assert report.channel == "new_sets"
    assert report.update.behind is True


def test_rendered_email_and_smtp_settings():
    r = RenderedEmail(subject="s", html="<p>", text="t", images=[("cid0", b"x")])
    assert r.images[0][0] == "cid0"
    smtp = SMTPSettings(
        host="h",
        port=587,
        security="starttls",
        user="u",
        password="p",
        from_address="f@x",
    )
    assert smtp.port == 587
