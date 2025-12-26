"""Tests for ISO operations."""

import pytest

from ps3toolbox.core.iso import get_iso_size
from ps3toolbox.core.iso import pad_iso_to_boundary
from ps3toolbox.core.iso import validate_iso


def test_get_iso_size(tmp_path):
    """Test getting ISO file size."""
    iso_file = tmp_path / "test.iso"
    test_data = b"test" * 1000
    iso_file.write_bytes(test_data)

    size = get_iso_size(iso_file)
    assert size == len(test_data)


def test_pad_iso_to_boundary(tmp_path):
    """Test padding ISO to boundary."""
    iso_file = tmp_path / "test.iso"
    iso_file.write_bytes(b"test" * 100)

    original_size = iso_file.stat().st_size
    padding_added = pad_iso_to_boundary(iso_file, 0x1000)
    new_size = iso_file.stat().st_size

    assert new_size % 0x1000 == 0
    assert new_size == original_size + padding_added


def test_pad_iso_already_aligned(tmp_path):
    """Test padding ISO that's already aligned."""
    iso_file = tmp_path / "test.iso"
    iso_file.write_bytes(b"test" * 1024)

    padding_added = pad_iso_to_boundary(iso_file, 0x1000)
    assert padding_added == 0


def test_validate_iso_missing_file(tmp_path):
    """Test validation with non-existent file."""
    iso_file = tmp_path / "nonexistent.iso"

    with pytest.raises(FileNotFoundError):
        validate_iso(iso_file)
