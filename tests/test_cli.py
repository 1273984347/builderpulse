"""Tests for CLI."""

from click.testing import CliRunner
from builderpulse.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "BuilderPulse" in result.output


def test_transcribe_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["transcribe", "--help"])
    assert result.exit_code == 0
    assert "engine" in result.output


def test_digest_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["digest", "--help"])
    assert result.exit_code == 0
    assert "sources" in result.output


def test_config_show():
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "language" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output
