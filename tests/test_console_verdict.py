"""Tests for the verdict one-line-per-file primitive."""
import pytest

from festival_organizer.console import verdict


def test_verdict_done_shape():
    row = verdict(
        status="done",
        index=1,
        total=5,
        filename="my_set.mkv",
        detail="Artist @ Stage . 25 chapters",
        elapsed_s=12.4,
    )
    plain = row.plain
    assert plain.startswith("  done")
    assert "[1/5]" in plain
    assert "my_set.mkv" in plain
    assert "->" in plain
    assert "Artist @ Stage . 25 chapters" in plain
    assert "12.4s" in plain


def test_verdict_skipped_no_elapsed():
    row = verdict(
        status="skipped",
        index=5,
        total=5,
        filename="other.mkv",
        detail="low confidence (score 135)",
        elapsed_s=0.1,
    )
    assert "0.1s" not in row.plain


def test_verdict_error_style():
    row = verdict(
        status="error",
        index=1,
        total=1,
        filename="broken.mkv",
        detail="mkvpropedit failed",
        elapsed_s=3.2,
    )
    spans_have_red = any(span.style == "red" for span in row.spans)
    assert spans_have_red


@pytest.mark.parametrize("status,expected_style", [
    ("done", "green"),
    ("updated", "cyan"),
    ("up-to-date", "dim green"),
    ("preview", "cyan"),
    ("skipped", "yellow"),
    ("error", "red"),
])
def test_verdict_badge_colours(status, expected_style):
    row = verdict(status=status, index=1, total=1, filename="f.mkv",
                  detail="x", elapsed_s=1.0)
    assert any(span.style == expected_style for span in row.spans)


def test_verdict_long_filename_truncated_preserves_bracketed_id():
    long = "A Very Long Filename That Overruns The Width [fLyb8KvtSzw].mkv"
    row = verdict(status="done", index=1, total=1, filename=long,
                  detail="x", elapsed_s=1.0, width=60)
    plain = row.plain
    assert "[fLyb8KvtSzw].mkv" in plain
    assert ".mkv" in plain
    assert "\u2026" in plain


def test_verdict_unknown_status_raises():
    with pytest.raises(ValueError):
        verdict(status="weird", index=1, total=1, filename="f.mkv",
                detail="x", elapsed_s=1.0)


@pytest.mark.parametrize("status", ["done", "updated", "up-to-date", "preview", "skipped", "error"])
def test_verdict_has_gap_between_badge_and_counter(status):
    """Every status must have at least 2 spaces between the badge label
    and the [i/N] counter. Regression: up-to-date (10 chars) previously
    collided with the counter when badge width was 11.
    """
    row = verdict(status=status, index=1, total=5, filename="f.mkv",
                  detail="x", elapsed_s=1.0)
    plain = row.plain
    # Find the badge label and verify what follows contains at least 2 spaces
    # before the counter.
    idx = plain.index("[1/5]")
    # Characters immediately before "[1/5]" must include >= 2 spaces.
    assert plain[idx - 2:idx] == "  ", (
        f"Expected 2-space gap before [i/N] for status={status}, "
        f"got: {plain!r}"
    )


def test_verdict_preview_shape():
    row = verdict(
        status="preview",
        index=1,
        total=5,
        filename="my_set.mkv",
        detail="would copy to Festivals/Ultra Miami 2026/",
        elapsed_s=0.0,
    )
    plain = row.plain
    assert plain.startswith("  preview")
    assert "[1/5]" in plain
    assert "would copy to" in plain
    # No elapsed shown for 0.0s (below 0.5s threshold)
    assert "0.0s" not in plain
