"""Tests for CLI interface."""

import pytest
from click.testing import CliRunner
from ps3toolbox.cli import cli


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test CLI help message."""
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'PS3 Toolbox' in result.output


def test_cli_version(runner):
    """Test CLI version command."""
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert '0.1.0' in result.output


def test_encrypt_help(runner):
    """Test encrypt command help."""
    result = runner.invoke(cli, ['encrypt', '--help'])
    assert result.exit_code == 0
    assert 'Encrypt PS2 ISO' in result.output


def test_decrypt_help(runner):
    """Test decrypt command help."""
    result = runner.invoke(cli, ['decrypt', '--help'])
    assert result.exit_code == 0
    assert 'Decrypt .BIN.ENC' in result.output


def test_batch_encrypt_help(runner):
    """Test batch-encrypt command help."""
    result = runner.invoke(cli, ['batch-encrypt', '--help'])
    assert result.exit_code == 0
    assert 'Batch encrypt' in result.output


def test_info_help(runner):
    """Test info command help."""
    result = runner.invoke(cli, ['info', '--help'])
    assert result.exit_code == 0
    assert 'information' in result.output
