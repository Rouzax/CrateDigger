import io
from types import SimpleNamespace

import festival_organizer.notify as notify
from festival_organizer.console import make_console
from festival_organizer.notify.models import (
    EmailSet,
    RunReport,
    SMTPSettings,
    UpdateInfo,
)


def _op(name, target=None):
    return SimpleNamespace(name=name, target=target)


def _res(name, status):
    return SimpleNamespace(name=name, status=status, detail="", display_name=name)


def _console_buf():
    """A console writing to an in-memory buffer (not a TTY, so spinners stay off)."""
    buf = io.StringIO()
    return make_console(file=buf), buf


class _FakeProgress:
    """Records StepProgress.update calls so tests can assert on counters."""

    def __init__(self):
        self.calls = []

    def update(self, step, *, filename=None, current=0, total=0):
        self.calls.append((step, current, total))


class _Cfg:
    """Minimal config stand-in exposing the email_* surface used by the orchestrator."""

    def __init__(self, enabled=True, to=("a@x",)):
        self._enabled, self._to = enabled, list(to)
        self.email_smtp_host = "mail.lan"
        self.email_smtp_port = 587
        self.email_smtp_security = "starttls"
        self.email_smtp_user = "u"
        self.email_smtp_password = "p"
        self.email_from_address = "cd@lan"
        self.email_thumbnail_width = 140

    def email_channel_enabled(self, ch):
        if ch == "update_reminder":
            return True
        return self._enabled

    def email_channel_recipients(self, ch):
        return list(self._to)

    def get_place_display(self, place, edition):
        return f"{place} {edition}".strip() if edition else place


def _report(channel="new_sets", n=1, update=None):
    sets = [
        EmailSet(
            f"Artist{i}", "UMF Miami", "2026", "", [], "19 tracks", None, "festival_set"
        )
        for i in range(n)
    ]
    return RunReport(channel=channel, sets=sets, update=update, stats={}, timestamp="t")


def test_resolve_should_send_flag_overrides():
    assert notify._should_send(_Cfg(enabled=False), "new_sets", flag=True) is True
    assert notify._should_send(_Cfg(enabled=True), "new_sets", flag=False) is False
    assert notify._should_send(_Cfg(enabled=True), "new_sets", flag=None) is True
    assert notify._should_send(_Cfg(enabled=False), "new_sets", flag=None) is False


def test_send_report_calls_sender_with_recipients(monkeypatch):
    sent = {}

    def fake_send(settings, rendered, *, to):
        sent["to"] = to
        sent["settings"] = settings
        sent["subject"] = rendered.subject

    monkeypatch.setattr(notify, "send_email", fake_send)
    notify._send_report(_Cfg(to=["a@x", "b@x"]), _report(), thumbnail_width=140)
    assert sent["to"] == ["a@x", "b@x"]
    assert isinstance(sent["settings"], SMTPSettings)
    assert sent["subject"].startswith("CrateDigger:")


def test_send_report_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(notify, "send_email", boom)
    notify._send_report(_Cfg(), _report(), thumbnail_width=140)  # must not raise


def test_empty_report_sends_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: calls.append(1))
    notify._send_report(_Cfg(), _report(n=0), thumbnail_width=140)
    assert calls == []


def test_update_reminder_throttled(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: calls.append(1))
    marker = tmp_path / "m.json"
    update = UpdateInfo("0.19.9", "0.20.0", True)
    monkeypatch.setattr(notify, "get_cached_update_status", lambda: update)

    cfg = _Cfg()
    notify.maybe_send_update_reminder(cfg, content_email_sent=False, marker_path=marker)
    notify.maybe_send_update_reminder(cfg, content_email_sent=False, marker_path=marker)
    assert len(calls) == 1


def test_update_reminder_suppressed_when_content_sent(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(
        notify, "get_cached_update_status", lambda: UpdateInfo("0.19.9", "0.20.0", True)
    )
    notify.maybe_send_update_reminder(
        _Cfg(), content_email_sent=True, marker_path=tmp_path / "m.json"
    )
    assert calls == []


def test_notify_new_sets_sends_and_then_reminder(monkeypatch, tmp_path):
    sent_channels = []
    monkeypatch.setattr(
        notify,
        "send_email",
        lambda settings, rendered, *, to: sent_channels.append(rendered.subject),
    )
    monkeypatch.setattr(
        notify, "get_cached_update_status", lambda: UpdateInfo("0.19.9", "0.20.0", True)
    )

    def _op(name, target):
        return SimpleNamespace(name=name, target=target)

    def _res(name, status):
        return SimpleNamespace(name=name, status=status, detail="", display_name=name)

    from tests.conftest import make_mediafile

    target = tmp_path / "v.mkv"
    mf = make_mediafile(
        source_path=target,
        artist="A",
        festival="UMF Miami",
        year="2026",
        content_type="festival_set",
        duration_seconds=5400.0,
    )
    notify.notify_new_sets(
        _Cfg(),
        pipeline_files=[(target, mf, [_op("organize", target)])],
        all_results=[[_res("organize", "done")]],
        stats={"added": 1, "up_to_date": 0, "errors": 0},
        flag=None,
        count_chapters=lambda p: 19,
        marker_path=tmp_path / "m.json",
    )
    assert len(sent_channels) == 1
    assert "new set" in sent_channels[0]


def test_notify_new_sets_disabled_still_sends_reminder(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        notify,
        "send_email",
        lambda settings, rendered, *, to: sent.append(rendered.subject),
    )
    monkeypatch.setattr(
        notify, "get_cached_update_status", lambda: UpdateInfo("0.19.9", "0.20.0", True)
    )
    cfg = _Cfg(enabled=False)
    notify.notify_new_sets(
        cfg,
        pipeline_files=[],
        all_results=[],
        stats={},
        flag=None,
        count_chapters=lambda p: None,
        marker_path=tmp_path / "m.json",
    )
    assert len(sent) == 1


def test_notify_updated_sets_sends(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        notify,
        "send_email",
        lambda settings, rendered, *, to: sent.append(rendered.subject),
    )
    monkeypatch.setattr(
        notify,
        "get_cached_update_status",
        lambda: UpdateInfo("0.20.0", "0.20.0", False),
    )
    from tests.conftest import make_mediafile

    path = tmp_path / "u.mkv"
    mf = make_mediafile(
        source_path=path,
        artist="Armin van Buuren",
        festival="ASOT",
        year="2026",
        content_type="festival_set",
    )
    notify.notify_updated_sets(
        _Cfg(),
        updated_paths=[path],
        analyse=lambda p: mf,
        count_chapters=lambda p: 41,
        flag=None,
        marker_path=tmp_path / "m.json",
    )
    assert len(sent) == 1
    assert "updated set" in sent[0]


def test_build_thumbs_reports_progress(tmp_path):
    from PIL import Image

    posters = []
    for i in range(3):
        p = tmp_path / f"p{i}-poster.jpg"
        Image.new("RGB", (200, 120), (10, 20, 30)).save(p, "JPEG")
        posters.append(p)
    sets = [
        EmailSet(f"A{i}", "E", "2026", "", [], "", posters[i], "festival_set")
        for i in range(3)
    ]
    report = RunReport(
        channel="new_sets", sets=sets, update=None, stats={}, timestamp="t"
    )
    prog = _FakeProgress()
    thumbs = notify._build_thumbs(report, 80, progress=prog)
    assert len(thumbs) == 3
    resize = [c for c in prog.calls if c[0] == "Resizing posters"]
    assert [c[1] for c in resize] == [1, 2, 3]  # 1-based current
    assert all(c[2] == 3 for c in resize)  # total


def test_notify_new_sets_prints_sent_verdict(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "send_email", lambda settings, rendered, *, to: None)
    monkeypatch.setattr(
        notify,
        "get_cached_update_status",
        lambda: UpdateInfo("0.20.0", "0.20.0", False),
    )
    from tests.conftest import make_mediafile

    target = tmp_path / "v.mkv"
    mf = make_mediafile(
        source_path=target,
        artist="A",
        festival="UMF Miami",
        year="2026",
        content_type="festival_set",
        duration_seconds=5400.0,
    )
    con, buf = _console_buf()
    notify.notify_new_sets(
        _Cfg(to=["a@x", "b@x"]),
        pipeline_files=[(target, mf, [_op("organize", target)])],
        all_results=[[_res("organize", "done")]],
        stats={"added": 1, "up_to_date": 0, "errors": 0},
        flag=None,
        count_chapters=lambda p: 19,
        marker_path=tmp_path / "m.json",
        console=con,
        suppressed=True,
    )
    out = buf.getvalue()
    assert "New-sets email" in out
    assert "sent to 2 recipients" in out


def test_notify_updated_sets_prints_error_verdict(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(notify, "send_email", boom)
    monkeypatch.setattr(
        notify,
        "get_cached_update_status",
        lambda: UpdateInfo("0.20.0", "0.20.0", False),
    )
    from tests.conftest import make_mediafile

    path = tmp_path / "u.mkv"
    mf = make_mediafile(
        source_path=path,
        artist="Armin van Buuren",
        festival="ASOT",
        year="2026",
        content_type="festival_set",
    )
    con, buf = _console_buf()
    notify.notify_updated_sets(
        _Cfg(),
        updated_paths=[path],
        analyse=lambda p: mf,
        count_chapters=lambda p: 41,
        flag=None,
        marker_path=tmp_path / "m.json",
        console=con,
        suppressed=True,
    )
    out = buf.getvalue()
    assert "Updated-sets email" in out
    assert "send failed" in out
    assert "OSError" in out


def test_notify_skip_is_silent_with_console(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: None)
    monkeypatch.setattr(
        notify,
        "get_cached_update_status",
        lambda: UpdateInfo("0.20.0", "0.20.0", False),
    )
    con, buf = _console_buf()
    # empty run -> no_changes -> skipped -> nothing printed
    notify.notify_new_sets(
        _Cfg(to=[]),
        pipeline_files=[],
        all_results=[],
        stats={},
        flag=None,
        count_chapters=lambda p: None,
        marker_path=tmp_path / "m.json",
        console=con,
        suppressed=True,
    )
    assert buf.getvalue().strip() == ""


def test_build_thumbs_capped(monkeypatch, tmp_path):
    from festival_organizer.notify.render import MAX_SETS

    poster = tmp_path / "p-poster.jpg"
    from PIL import Image

    Image.new("RGB", (1920, 1080), (40, 40, 60)).save(poster, "JPEG")
    sets = [
        EmailSet(f"A{i}", "E", "2026", "", [], "", poster, "festival_set")
        for i in range(MAX_SETS + 10)
    ]
    report = RunReport(
        channel="new_sets", sets=sets, update=None, stats={}, timestamp="t"
    )
    thumbs = notify._build_thumbs(report, 140)
    assert len(thumbs) == MAX_SETS  # capped, not MAX_SETS+10


def test_notify_test_sends_sample(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        notify,
        "send_email",
        lambda settings, rendered, *, to: captured.update(
            to=to, subject=rendered.subject, html=rendered.html
        ),
    )
    recipients = notify.notify_test(_Cfg(to=["me@x"]))
    assert recipients == ["me@x"]
    assert captured["to"] == ["me@x"]
    assert "CrateDigger" in captured["subject"]
    assert "Sample" in captured["html"]


def test_notify_test_raises_without_recipients():
    import pytest

    with pytest.raises(ValueError, match="recipients"):
        notify.notify_test(_Cfg(to=[]))


def test_notify_test_raises_without_smtp_host():
    import pytest

    cfg = _Cfg(to=["me@x"])
    cfg.email_smtp_host = ""
    with pytest.raises(ValueError, match="smtp_host"):
        notify.notify_test(cfg)


def test_notify_test_propagates_transport_error(monkeypatch):
    import pytest

    def boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(notify, "send_email", boom)
    with pytest.raises(OSError):
        notify.notify_test(_Cfg(to=["me@x"]))
