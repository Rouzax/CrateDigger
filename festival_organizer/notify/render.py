"""Render a RunReport into a house-styled multipart HTML + text email."""
from __future__ import annotations

from collections import OrderedDict
from html import escape

from festival_organizer.notify.models import RenderedEmail, RunReport

# House style (mirrors site/style.css)
ACCENT = "#e8734a"
ACCENT_SOFT = "#d4845e"
BG = "#06060c"
CARD = "#101019"
BORDER = "#1b1b27"
TEXT = "#f0f0f5"
MUTED = "#8888a0"
MUTED2 = "#555570"
FONT = "'Outfit',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace"


def _is_concert(s) -> bool:
    return s.kind == "concert_film" or not s.event


def _pills(genres) -> str:
    return "".join(
        f'<span style="display:inline-block;background:rgba(232,115,74,0.08);'
        f'color:{ACCENT_SOFT};font-size:10px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.1em;padding:4px 10px;border-radius:20px;margin:0 6px 0 0;">'
        f'{escape(g)}</span>'
        for g in genres
    )


def _row(s, thumb_cid: str | None) -> str:
    if thumb_cid:
        img = (f'<img src="cid:{thumb_cid}" width="140" '
               f'style="display:block;width:140px;height:auto;border-radius:7px;'
               f'border:1px solid {BORDER};">')
    else:
        img = (f'<div style="width:140px;height:79px;border-radius:7px;'
               f'background:{CARD};border:1px solid {BORDER};"></div>')
    note = f' &middot; <span style="color:{ACCENT}">{escape(s.note)}</span>' if s.note else ""
    meta = (f'<div style="font-size:12px;color:{MUTED};margin-top:9px;">{escape(s.metric)}</div>'
            if s.metric else "")
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;"><tr>'
        f'<td valign="top" width="140" style="padding:0;">{img}</td>'
        f'<td valign="top" style="padding:2px 0 0 16px;">'
        f'<div style="font-size:16px;color:{TEXT};font-weight:700;line-height:1.25;">{escape(s.artist)}</div>'
        f'<div style="font-size:13px;color:{MUTED};margin-top:4px;">'
        f'<span style="font-family:{MONO};">{escape(s.year)}</span>{note}</div>'
        f'<div style="margin-top:9px;">{_pills(s.genres)}</div>'
        f'{meta}</td></tr></table>'
    )


def _group_header(label: str, count: int) -> str:
    word = "set" if count == 1 else "sets"
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 14px 0;"><tr>'
        f'<td valign="middle" style="white-space:nowrap;">'
        f'<span style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{ACCENT};font-weight:700;">{label}</span>'
        f'<span style="font-family:{MONO};font-size:11px;color:{MUTED2};margin-left:8px;">{count} {word}</span></td>'
        f'<td valign="middle" width="100%" style="padding-left:14px;">'
        f'<div style="height:1px;background:{BORDER};"></div></td></tr></table>'
    )


def _update_banner(update) -> str:
    if not update or not update.behind:
        return ""
    return (
        f'<div style="background:rgba(232,115,74,0.06);border:1px solid rgba(232,115,74,0.25);'
        f'border-radius:12px;padding:13px 16px;margin:0 0 18px 0;">'
        f'<strong style="color:{TEXT};font-size:13px;">CrateDigger update available</strong><br>'
        f'<span style="color:{MUTED};font-size:13px;">You\'re on '
        f'<span style="font-family:{MONO};">{escape(update.installed)}</span>, latest is '
        f'<span style="font-family:{MONO};color:{ACCENT};font-weight:600;">{escape(update.latest or "")}</span>.'
        f'</span></div>'
    )


def render(report: RunReport, thumbs: dict) -> RenderedEmail:
    """Render the report. `thumbs` maps set index -> (cid, jpeg bytes)."""
    festival_sets, concert_sets = [], []
    for idx, s in enumerate(report.sets):
        (concert_sets if _is_concert(s) else festival_sets).append((idx, s))

    body_parts = [_update_banner(report.update)]
    text_lines = []

    # Festival groups by event, newest year first
    by_event = OrderedDict()
    for idx, s in festival_sets:
        by_event.setdefault(s.event, []).append((idx, s))
    ordered = sorted(by_event.items(),
                     key=lambda kv: max(x[1].year for x in kv[1]), reverse=True)
    for event, items in ordered:
        items = sorted(items, key=lambda it: (it[1].year, it[1].artist), reverse=False)
        items = sorted(items, key=lambda it: it[1].year, reverse=True)
        body_parts.append(_group_header(escape(event), len(items)))
        text_lines.append(f"\n{event}")
        for idx, s in items:
            cid = thumbs.get(idx, (None,))[0]
            body_parts.append(_row(s, cid))
            text_lines.append(f"  - {s.artist} ({s.year}) {s.metric}".rstrip())

    # Concerts grouped by artist
    if concert_sets:
        body_parts.append(_group_header("Concerts & Albums", len(concert_sets)))
        text_lines.append("\nConcerts & Albums")
        for idx, s in sorted(concert_sets, key=lambda it: it[1].artist):
            cid = thumbs.get(idx, (None,))[0]
            body_parts.append(_row(s, cid))
            text_lines.append(f"  - {s.artist} ({s.year}) {s.metric}".rstrip())

    n = len(report.sets)
    events = len({s.event for _i, s in festival_sets if s.event})
    if report.channel == "updated_sets":
        heading = f"{n} updated set{'s' if n != 1 else ''}"
        subject = f"CrateDigger: {n} updated set{'s' if n != 1 else ''}"
    else:
        heading = f"{n} new set{'s' if n != 1 else ''}"
        subject = f"CrateDigger: {n} new set{'s' if n != 1 else ''}"
        if events:
            subject += f" across {events} event{'s' if n != 1 else ''}"

    header = (
        f'<div style="padding:30px 28px 20px 28px;border-bottom:1px solid {BORDER};'
        f'background:radial-gradient(ellipse at top left, rgba(232,115,74,0.12), transparent 60%);">'
        f'<div style="font-size:11px;letter-spacing:.14em;color:{ACCENT};font-weight:700;">CRATEDIGGER</div>'
        f'<div style="font-size:26px;color:{TEXT};font-weight:700;margin-top:6px;">{escape(heading)}</div>'
        f'<div style="font-size:13px;color:{MUTED};margin-top:5px;">{escape(report.host)} &middot; '
        f'<span style="font-family:{MONO};">{escape(report.timestamp)}</span></div></div>'
    )
    stats = report.stats or {}
    footer = (
        f'<div style="padding:18px 28px;border-top:1px solid {BORDER};color:{MUTED2};font-size:11px;">'
        f'{stats.get("added", 0)} added &middot; {stats.get("up_to_date", 0)} up to date &middot; '
        f'{stats.get("errors", 0)} errors</div>'
    )
    html = (
        f'<div style="max-width:620px;margin:0 auto;background:{BG};border-radius:20px;'
        f'overflow:hidden;border:1px solid {BORDER};font-family:{FONT};">'
        f'{header}<div style="padding:20px 24px;">{"".join(body_parts)}</div>{footer}</div>'
    )

    text = f"{heading} on {report.host} ({report.timestamp})\n" + "\n".join(text_lines)
    if report.update and report.update.behind:
        text += f"\n\nCrateDigger update available: {report.update.installed} -> {report.update.latest}"

    images = [thumbs[idx] for idx in sorted(thumbs)]
    return RenderedEmail(subject=subject, html=html, text=text, images=images)
