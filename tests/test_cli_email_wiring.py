import festival_organizer.notify as notify
from festival_organizer import cli as cli_mod


def test_chapter_counter_and_analyse_imports_exist():
    from festival_organizer.tracklists.chapters import extract_existing_chapters
    from festival_organizer.analyzer import analyse_file
    assert callable(extract_existing_chapters)
    assert callable(analyse_file)


def test_notify_entry_points_are_public():
    assert hasattr(notify, "notify_new_sets")
    assert hasattr(notify, "notify_updated_sets")
    assert hasattr(notify, "notify_test")


def test_top_level_email_test_flag_sends(monkeypatch):
    from typer.testing import CliRunner

    # cli imports `notify` locally, so patch the live module attribute.
    monkeypatch.setattr(notify, "notify_test", lambda config: ["me@x", "you@x"])
    result = CliRunner().invoke(cli_mod.app, ["--email-test"])
    assert result.exit_code == 0
    assert "Test email sent to me@x, you@x" in result.stdout


def test_top_level_email_test_flag_reports_misconfig(monkeypatch):
    from typer.testing import CliRunner

    def boom(config):
        raise ValueError("no recipients configured under [email.new_sets].to")

    monkeypatch.setattr(notify, "notify_test", boom)
    result = CliRunner().invoke(cli_mod.app, ["--email-test"])
    assert result.exit_code == 1
    assert "Email not configured" in result.stdout


def _option_names(command):
    """All option strings for a click command (introspection, not rendered help).

    Parsing `--help` output is fragile: Typer renders it with Rich, which wraps
    option names at the terminal width, so a narrow CI terminal splits e.g.
    "--email-test" across lines and a substring check fails. Inspect the command
    objects instead.
    """
    names = []
    for p in command.params:
        names += list(getattr(p, "opts", [])) + list(getattr(p, "secondary_opts", []))
    return names


def test_organize_no_longer_has_email_test_flag():
    import typer
    group = typer.main.get_command(cli_mod.app)
    org_opts = _option_names(group.commands["organize"])
    assert "--email-test" not in org_opts   # moved to the top-level command
    assert "--email" in org_opts            # per-run override still present


def test_top_level_has_email_test_flag():
    import typer
    group = typer.main.get_command(cli_mod.app)
    top_opts = _option_names(group)   # callback options live on the group
    assert "--email-test" in top_opts
    assert "--check" in top_opts
