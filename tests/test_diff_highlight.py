"""Tests for the _diff_highlight helper that colors changed segments."""
from rich.text import Text

from festival_organizer.console import _diff_highlight


def test_identical_strings_no_style():
    result = _diff_highlight("hello.mkv", "hello.mkv")
    assert result.plain == "hello.mkv"
    assert len(result.spans) == 0


def test_single_insertion_styled():
    source = "2026 - FISHER [Bay Oval Park].mkv"
    target = "2026 - FISHER - Bay Oval Park [Bay Oval Park].mkv"
    result = _diff_highlight(source, target)
    assert result.plain == target
    styled_text = "".join(
        result.plain[span.start:span.end]
        for span in result.spans
        if span.style == "orange1"
    )
    assert " - Bay Oval Park" in styled_text


def test_full_replacement_when_disjoint():
    source = "AFROJACK LIVE @ ULTRA MUSIC FESTIVAL [fLyb8KvtSzw].mkv"
    target = "2026 - Afrojack - Ultra Music Festival Miami [Mainstage].mkv"
    result = _diff_highlight(source, target)
    assert result.plain == target
    styled_chars = sum(
        span.end - span.start
        for span in result.spans
        if span.style == "orange1"
    )
    assert styled_chars == len(target)


def test_empty_source_styles_entire_target():
    result = _diff_highlight("", "new_name.mkv")
    assert result.plain == "new_name.mkv"
    styled_chars = sum(
        span.end - span.start
        for span in result.spans
        if span.style == "orange1"
    )
    assert styled_chars == len("new_name.mkv")


def test_empty_target_returns_empty():
    result = _diff_highlight("old.mkv", "")
    assert result.plain == ""


def test_custom_style():
    result = _diff_highlight("a.mkv", "b.mkv", change_style="bold red")
    assert any(span.style == "bold red" for span in result.spans)
