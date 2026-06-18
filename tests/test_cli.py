from typer.testing import CliRunner

from ocr_grade import __version__
from ocr_grade.cli import app

runner = CliRunner()


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "dry-run", "purge", "version"):
        assert command in result.output


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output
