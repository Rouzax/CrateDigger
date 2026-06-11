from pathlib import Path

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
