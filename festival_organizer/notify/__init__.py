"""Email notifications for run summaries and update reminders.

Orchestration entry points. All public helpers swallow and log errors so a run
never fails because of email.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from festival_organizer.notify import throttle
from festival_organizer.notify.collect import collect_new_sets, collect_updated_sets
from festival_organizer.notify.models import EmailSet, RunReport, SMTPSettings, UpdateInfo
from festival_organizer.notify.render import render, MAX_SETS
from festival_organizer.notify.send import send_email
from festival_organizer.notify.thumbnails import make_thumbnail
from festival_organizer.update_check import get_cached_update_status

_log = logging.getLogger("festival_organizer.notify")


def _should_send(config, channel: str, *, flag: bool | None) -> bool:
    """Resolve whether to send `channel`: explicit flag wins over config."""
    if flag is not None:
        return flag
    return config.email_channel_enabled(channel)


def _smtp_settings(config) -> SMTPSettings:
    return SMTPSettings(
        host=config.email_smtp_host,
        port=config.email_smtp_port,
        security=config.email_smtp_security,
        user=config.email_smtp_user,
        password=config.email_smtp_password,
        from_address=config.email_from_address,
    )


def _build_thumbs(report: RunReport, width: int) -> dict:
    thumbs = {}
    for idx, s in enumerate(report.sets):
        if idx >= MAX_SETS:
            break
        if not s.poster_path:
            continue
        try:
            thumbs[idx] = (f"poster{idx}", make_thumbnail(s.poster_path, width))
        except Exception as e:
            _log.warning("notify.thumbnail_failed: file=%s error=\"%s\"", s.poster_path, e)
    return thumbs


def _send_report(config, report: RunReport, *, thumbnail_width: int) -> bool:
    """Render and send a report. Returns True if an email was actually sent."""
    if not report.sets:
        _log.info("email.skipped: channel=%s reason=no_changes", report.channel)
        return False
    to = config.email_channel_recipients(report.channel)
    if not to:
        _log.info("email.skipped: channel=%s reason=no_recipients", report.channel)
        return False
    try:
        thumbs = _build_thumbs(report, thumbnail_width)
        rendered = render(report, thumbs)
        send_email(_smtp_settings(config), rendered, to=to)
        _log.info("email.sent: channel=%s recipients=%d sets=%d",
                  report.channel, len(to), len(report.sets))
        return True
    except Exception as e:
        _log.warning("email.failed: channel=%s error=\"%s\"", report.channel, e)
        return False


def maybe_send_update_reminder(config, *, content_email_sent: bool,
                               marker_path: Path | None = None) -> None:
    """Send a standalone update reminder, throttled once per version, deduped
    against content emails (which already carry the banner)."""
    if content_email_sent:
        return
    if not config.email_channel_enabled("update_reminder"):
        return
    to = config.email_channel_recipients("update_reminder")
    if not to:
        return
    try:
        update = get_cached_update_status()
    except Exception as e:
        _log.warning("email.update_status_failed: error=\"%s\"", e)
        return
    if not update.behind or not update.latest:
        return
    if throttle.already_notified(update.latest, marker_path=marker_path):
        return
    report = RunReport(channel="update_reminder", sets=[], update=update,
                       stats={}, timestamp="")
    try:
        rendered = render(report, thumbs={})
        send_email(_smtp_settings(config), rendered, to=to)
        throttle.record_notified(update.latest, marker_path=marker_path)
        _log.info("email.sent: channel=update_reminder version=%s", update.latest)
    except Exception as e:
        _log.warning("email.failed: channel=update_reminder error=\"%s\"", e)


def _now() -> str:
    return datetime.now().strftime("%d %b %Y, %H:%M")


def notify_new_sets(config, *, pipeline_files, all_results, stats, flag,
                    count_chapters, marker_path=None) -> None:
    """End-of-organize hook: send the new-sets email (if warranted), then the
    standalone update reminder (suppressed if a content email went out)."""
    content_sent = False
    if _should_send(config, "new_sets", flag=flag):
        try:
            update = get_cached_update_status()
        except Exception:
            update = None
        report = collect_new_sets(
            pipeline_files, all_results,
            update=update, stats=stats, timestamp=_now(),
            count_chapters=count_chapters,
        )
        content_sent = _send_report(config, report,
                                    thumbnail_width=config.email_thumbnail_width)
    maybe_send_update_reminder(config, content_email_sent=content_sent,
                               marker_path=marker_path)


def _sample_report() -> RunReport:
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample-poster.jpg"
    poster = fixture if fixture.exists() else None
    sets = [
        EmailSet("Sample Artist One", "UMF Miami", "2026", "Mainstage",
                 ["Techno"], "19 tracks · 1h 30m", poster, "festival_set"),
        EmailSet("Sample Artist Two", "Coachella", "2026", "",
                 ["House"], "22 tracks · 1h 12m", poster, "festival_set"),
    ]
    return RunReport(channel="new_sets", sets=sets,
                     update=UpdateInfo("0.19.9", "0.20.0", True),
                     stats={"added": 2, "up_to_date": 5, "errors": 0},
                     timestamp=_now())


def notify_test(config) -> list[str]:
    """Send a sample email to the new-sets recipients to verify SMTP + rendering.

    Returns the list of recipients it sent to. Unlike the end-of-run hooks, this
    does NOT swallow errors: it raises ValueError when email is not configured
    (no recipients, or no SMTP host), and lets transport errors propagate, so the
    standalone `--email-test` command can report success or failure to the user.
    """
    to = config.email_channel_recipients("new_sets")
    if not to:
        raise ValueError("no recipients configured under [email.new_sets].to")
    if not config.email_smtp_host:
        raise ValueError("smtp_host is not set under [email]")
    report = _sample_report()
    thumbs = _build_thumbs(report, config.email_thumbnail_width)
    rendered = render(report, thumbs)
    send_email(_smtp_settings(config), rendered, to=to)
    _log.info("email.test_sent: recipients=%d", len(to))
    return to


def notify_updated_sets(config, *, updated_paths, analyse, count_chapters, flag,
                        run_stats=None, marker_path=None) -> None:
    """End-of-identify hook: send the updated-sets email (if warranted), then the
    standalone update reminder (suppressed if a content email went out)."""
    content_sent = False
    if _should_send(config, "updated_sets", flag=flag):
        try:
            update = get_cached_update_status()
        except Exception:
            update = None
        report = collect_updated_sets(
            updated_paths, analyse=analyse, count_chapters=count_chapters,
            update=update, timestamp=_now(), stats=run_stats,
        )
        content_sent = _send_report(config, report,
                                    thumbnail_width=config.email_thumbnail_width)
    maybe_send_update_reminder(config, content_email_sent=content_sent,
                               marker_path=marker_path)
