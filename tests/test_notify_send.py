from festival_organizer.notify.models import RenderedEmail, SMTPSettings
from festival_organizer.notify.send import build_message, send_email


def _rendered():
    return RenderedEmail(
        subject="CrateDigger: 1 new set",
        html="<p>hi</p>",
        text="hi",
        images=[("poster0", b"\xff\xd8jpeg")],
    )


def test_build_message_structure_and_cids():
    msg = build_message(_rendered(), from_address="cd@lan", to=["a@x", "b@x"])
    assert msg["Subject"] == "CrateDigger: 1 new set"
    assert msg["From"] == "cd@lan"
    assert msg["To"] == "a@x, b@x"
    raw = msg.as_string()
    assert "text/plain" in raw
    assert "text/html" in raw
    assert "<poster0>" in raw


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, pw):
        self.logged_in = (user, pw)

    def send_message(self, msg):
        self.sent = msg


def test_send_email_starttls_and_login(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr("festival_organizer.notify.send.smtplib.SMTP", _FakeSMTP)
    settings = SMTPSettings(
        host="mail.lan",
        port=587,
        security="starttls",
        user="u",
        password="p",
        from_address="cd@lan",
    )
    send_email(settings, _rendered(), to=["a@x"])
    inst = _FakeSMTP.instances[-1]
    assert inst.started_tls is True
    assert inst.logged_in == ("u", "p")
    assert inst.sent is not None
