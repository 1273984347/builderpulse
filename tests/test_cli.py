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


# ── Session 32: --role-model CLI option tests (M1 完善) ──────────


def test_process_role_model_help():
    """--role-model 应出现在 process --help 中."""
    runner = CliRunner()
    result = runner.invoke(cli, ["process", "--help"])
    assert result.exit_code == 0
    assert "--role-model" in result.output
    assert "extract" in result.output  # 列出 4 角色之一
    assert "translate" in result.output


def test_process_role_model_accepted():
    """--role-model 选项应被 click 接受 (不报 unknown option)."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process",
            "https://example.com",
            "--role-model",
            "extract=claude-opus-4-7,translate=ollama/llama3,query=gpt-4o",
        ],
    )
    # 即使 URL 被 is_safe_url 拒, --role-model 解析阶段应先执行, 不报 unknown option
    assert "no such option" not in result.output.lower()
    assert "unknown option" not in result.output.lower()


def test_process_role_model_single():
    """单 pair 解析: --role-model extract=claude-opus-4-7."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["process", "https://example.com", "--role-model", "extract=claude-opus-4-7"],
    )
    # 应该 non-zero exit (URL is_safe_url 失败) 但 --role-model 解析不报错
    assert "no such option" not in result.output.lower()
