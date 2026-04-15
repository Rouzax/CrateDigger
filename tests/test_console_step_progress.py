"""Tests for StepProgress transient spinner."""
import io
import threading

import pytest

from festival_organizer.console import StepProgress, make_console


def test_step_progress_disabled_is_noop_when_not_enabled():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    with sp:
        sp.update("Doing work")  # must not raise
    assert sp.live is None


def test_step_progress_update_stores_state():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    sp.update("Searching 1001TL", filename="foo.mkv", current=2, total=5)
    assert sp.step == "Searching 1001TL"
    assert sp.filename == "foo.mkv"
    assert sp.current == 2
    assert sp.total == 5


def test_step_progress_render_includes_counter():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    sp.update("Fetching tracklist", current=3, total=7)
    text = sp._render()
    assert "3/7" in text.plain
    assert "Fetching tracklist" in text.plain


def test_step_progress_render_without_counter():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    sp.update("Signing in")
    text = sp._render()
    assert "Signing in" in text.plain
    assert "/" not in text.plain


def test_step_progress_context_cleans_up_on_exception():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    with pytest.raises(RuntimeError):
        with sp:
            sp.update("Working")
            raise RuntimeError("boom")
    assert sp.live is None


def test_step_progress_stop_and_start():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)
    with sp:
        sp.update("Phase 1")
        sp.stop()
        assert sp.live is None
        sp.start()
        assert sp.live is None  # still None because enabled=False


def test_step_progress_thread_safe_update():
    con = make_console(file=io.StringIO())
    sp = StepProgress(con, enabled=False)

    def worker():
        for _ in range(50):
            sp.update("Step", current=1, total=2)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
