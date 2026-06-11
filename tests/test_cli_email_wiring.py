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


def test_organize_no_longer_has_email_test_flag():
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli_mod.app, ["organize", "--help"])
    assert result.exit_code == 0
    assert "--email-test" not in result.stdout   # moved to the top-level command
    assert "--email" in result.stdout            # per-run override still present


def test_top_level_help_lists_email_test():
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli_mod.app, ["--help"])
    assert result.exit_code == 0
    assert "--email-test" in result.stdout
