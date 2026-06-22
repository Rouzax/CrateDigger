from festival_organizer import update_check
from festival_organizer.notify.models import UpdateInfo


def test_get_cached_update_status_behind(monkeypatch):
    monkeypatch.setattr(
        update_check, "_read_cache", lambda: {"latest_version": "9.9.9"}
    )
    monkeypatch.setattr(update_check, "version", lambda _pkg: "0.19.9")
    info = update_check.get_cached_update_status()
    assert isinstance(info, UpdateInfo)
    assert info.installed == "0.19.9"
    assert info.latest == "9.9.9"
    assert info.behind is True


def test_get_cached_update_status_current(monkeypatch):
    monkeypatch.setattr(
        update_check, "_read_cache", lambda: {"latest_version": "0.19.9"}
    )
    monkeypatch.setattr(update_check, "version", lambda _pkg: "0.19.9")
    info = update_check.get_cached_update_status()
    assert info.behind is False


def test_get_cached_update_status_no_cache(monkeypatch):
    monkeypatch.setattr(update_check, "_read_cache", lambda: None)
    monkeypatch.setattr(update_check, "version", lambda _pkg: "0.19.9")
    info = update_check.get_cached_update_status()
    assert info.latest is None
    assert info.behind is False
