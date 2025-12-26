"""Tests for PS2 header operations."""

import pytest

from ps3toolbox.core.keys import PS2_PLACEHOLDER_CID
from ps3toolbox.core.keys import SEGMENT_SIZE
from ps3toolbox.ps2.header import build_ps2_header
from ps3toolbox.ps2.header import parse_ps2_header
from ps3toolbox.ps2.header import verify_header


def test_build_ps2_header():
    """Test PS2 header building."""
    header = build_ps2_header(PS2_PLACEHOLDER_CID, "ISO.BIN.ENC", 0x10000000)

    assert len(header) == SEGMENT_SIZE
    assert header[0:4] == b"PS2\x00"
    assert PS2_PLACEHOLDER_CID.encode("ascii") in header


def test_parse_ps2_header():
    """Test PS2 header parsing."""
    header = build_ps2_header(PS2_PLACEHOLDER_CID, "ISO.BIN.ENC", 0x10000000)
    metadata = parse_ps2_header(header)

    assert metadata["magic"] == "PS2\x00"
    assert metadata["version_major"] == 1
    assert metadata["version_minor"] == 1
    assert metadata["content_id"] == PS2_PLACEHOLDER_CID
    assert metadata["segment_size"] == SEGMENT_SIZE
    assert metadata["iso_size"] == 0x10000000


def test_verify_header_valid():
    """Test header verification with valid header."""
    header = build_ps2_header(PS2_PLACEHOLDER_CID, "ISO.BIN.ENC", 0x10000000)
    assert verify_header(header) is True


def test_verify_header_invalid_magic():
    """Test header verification with invalid magic."""
    header = bytearray(SEGMENT_SIZE)
    header[0:4] = b"BAD\x00"
    assert verify_header(bytes(header)) is False


def test_verify_header_too_short():
    """Test header verification with insufficient data."""
    header = b"PS2\x00" + bytes(100)
    assert verify_header(header) is False


def test_parse_invalid_header():
    """Test parsing invalid header raises error."""
    invalid_header = bytes(SEGMENT_SIZE)

    with pytest.raises(ValueError, match="Invalid PS2 header magic"):
        parse_ps2_header(invalid_header)
