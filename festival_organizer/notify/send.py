"""Assemble and send the multipart email via stdlib smtplib."""

from __future__ import annotations

import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from festival_organizer.notify.models import RenderedEmail, SMTPSettings

_TIMEOUT = 30


def build_message(
    rendered: RenderedEmail, *, from_address: str, to: list[str]
) -> MIMEMultipart:
    """Build a multipart/related message: alternative(text, html) + inline images."""
    root = MIMEMultipart("related")
    root["Subject"] = rendered.subject
    root["From"] = from_address
    root["To"] = ", ".join(to)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(rendered.text, "plain", "utf-8"))
    alt.attach(MIMEText(rendered.html, "html", "utf-8"))
    root.attach(alt)

    for cid, data in rendered.images:
        img = MIMEImage(data, "jpeg")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.jpg")
        root.attach(img)
    return root


def send_email(
    settings: SMTPSettings, rendered: RenderedEmail, *, to: list[str]
) -> None:
    """Send the rendered email to `to` using `settings`. Raises on transport failure."""
    msg = build_message(rendered, from_address=settings.from_address, to=to)
    if settings.security == "ssl":
        with smtplib.SMTP_SSL(settings.host, settings.port, timeout=_TIMEOUT) as server:
            if settings.user:
                server.login(settings.user, settings.password)
            server.send_message(msg)
        return
    with smtplib.SMTP(settings.host, settings.port, timeout=_TIMEOUT) as server:
        if settings.security == "starttls":
            server.starttls()
        if settings.user:
            server.login(settings.user, settings.password)
        server.send_message(msg)
