from festival_organizer.config import Config, DEFAULT_CONFIG


def test_email_defaults_disabled():
    c = Config({})
    assert c.email_smtp_host == ""
    assert c.email_smtp_port == 587
    assert c.email_thumbnail_width == 140
    assert c.email_channel_enabled("new_sets") is False
    assert c.email_channel_recipients("new_sets") == []


def test_email_channel_reads_subtables():
    c = Config(
        {
            "email": {
                "smtp_host": "mail.lan",
                "from_address": "cd@lan",
                "new_sets": {"enabled": True, "to": ["a@x", "b@x"]},
                "updated_sets": {"enabled": True, "to": ["a@x"]},
                "update_reminder": {"enabled": False, "to": ["a@x"]},
            }
        }
    )
    assert c.email_smtp_host == "mail.lan"
    assert c.email_from_address == "cd@lan"
    assert c.email_channel_enabled("new_sets") is True
    assert c.email_channel_recipients("new_sets") == ["a@x", "b@x"]
    assert c.email_channel_enabled("update_reminder") is False


def test_email_password_env_overrides(monkeypatch):
    monkeypatch.setenv("CRATEDIGGER_SMTP_PASSWORD", "envpw")
    c = Config({"email": {"smtp_password": "filepw"}})
    assert c.email_smtp_password == "envpw"


def test_default_config_has_email_section():
    assert "email" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["email"]["smtp_port"] == 587
