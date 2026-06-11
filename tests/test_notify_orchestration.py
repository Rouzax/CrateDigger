from pathlib import Path
from types import SimpleNamespace

import festival_organizer.notify as notify
from festival_organizer.notify.models import EmailSet, RunReport, UpdateInfo, SMTPSettings


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


def _report(channel="new_sets", n=1, update=None):
    sets = [EmailSet(f"Artist{i}", "UMF Miami", "2026", "", [], "19 tracks",
                     None, "festival_set") for i in range(n)]
    return RunReport(channel=channel, sets=sets, update=update,
                     stats={}, host="h", timestamp="t")


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
    monkeypatch.setattr(notify, "get_cached_update_status",
                        lambda: UpdateInfo("0.19.9", "0.20.0", True))
    notify.maybe_send_update_reminder(_Cfg(), content_email_sent=True,
                                      marker_path=tmp_path / "m.json")
    assert calls == []


def test_notify_new_sets_sends_and_then_reminder(monkeypatch, tmp_path):
    sent_channels = []
    monkeypatch.setattr(notify, "send_email",
                        lambda settings, rendered, *, to: sent_channels.append(rendered.subject))
    monkeypatch.setattr(notify, "get_cached_update_status",
                        lambda: UpdateInfo("0.19.9", "0.20.0", True))

    def _op(name, target):
        return SimpleNamespace(name=name, target=target)

    def _res(name, status):
        return SimpleNamespace(name=name, status=status, detail="", display_name=name)

    from tests.conftest import make_mediafile
    target = tmp_path / "v.mkv"
    mf = make_mediafile(source_path=target, artist="A", festival="UMF Miami", year="2026",
                        content_type="festival_set", duration_seconds=5400.0)
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
    monkeypatch.setattr(notify, "send_email",
                        lambda settings, rendered, *, to: sent.append(rendered.subject))
    monkeypatch.setattr(notify, "get_cached_update_status",
                        lambda: UpdateInfo("0.19.9", "0.20.0", True))
    cfg = _Cfg(enabled=False)
    notify.notify_new_sets(
        cfg, pipeline_files=[], all_results=[], stats={}, flag=None,
        count_chapters=lambda p: None, marker_path=tmp_path / "m.json",
    )
    assert len(sent) == 1


def test_notify_updated_sets_sends(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(notify, "send_email",
                        lambda settings, rendered, *, to: sent.append(rendered.subject))
    monkeypatch.setattr(notify, "get_cached_update_status",
                        lambda: UpdateInfo("0.20.0", "0.20.0", False))
    from tests.conftest import make_mediafile
    path = tmp_path / "u.mkv"
    mf = make_mediafile(source_path=path, artist="Armin van Buuren", festival="ASOT",
                        year="2026", content_type="festival_set")
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


def test_build_thumbs_capped(monkeypatch, tmp_path):
    from festival_organizer.notify.render import MAX_SETS
    poster = tmp_path / "p-poster.jpg"
    from PIL import Image
    Image.new("RGB", (1920, 1080), (40, 40, 60)).save(poster, "JPEG")
    sets = [EmailSet(f"A{i}", "E", "2026", "", [], "", poster, "festival_set")
            for i in range(MAX_SETS + 10)]
    report = RunReport(channel="new_sets", sets=sets, update=None, stats={}, host="h", timestamp="t")
    thumbs = notify._build_thumbs(report, 140)
    assert len(thumbs) == MAX_SETS    # capped, not MAX_SETS+10


def test_notify_test_sends_sample(monkeypatch):
    captured = {}
    monkeypatch.setattr(notify, "send_email",
                        lambda settings, rendered, *, to: captured.update(
                            to=to, subject=rendered.subject, html=rendered.html))
    notify.notify_test(_Cfg(to=["me@x"]))
    assert captured["to"] == ["me@x"]
    assert "CrateDigger" in captured["subject"]
    assert "Sample" in captured["html"]
