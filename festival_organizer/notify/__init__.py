"""Email notifications for run summaries and update reminders.

Orchestration entry points. All public helpers swallow and log errors so a run
never fails because of email.
"""
from __future__ import annotations

import logging
from pathlib import Path

from festival_organizer.notify import throttle
from festival_organizer.notify.models import RunReport, SMTPSettings
from festival_organizer.notify.render import render
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
                       stats={}, host="", timestamp="")
    try:
        rendered = render(report, thumbs={})
        send_email(_smtp_settings(config), rendered, to=to)
        throttle.record_notified(update.latest, marker_path=marker_path)
        _log.info("email.sent: channel=update_reminder version=%s", update.latest)
    except Exception as e:
        _log.warning("email.failed: channel=update_reminder error=\"%s\"", e)
