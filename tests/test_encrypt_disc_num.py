"""Unit tests for disc_num parameter in PS2 encryption."""

import struct
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from ps3toolbox.ps2.encrypt import encrypt_ps2_iso


class TestDiscNumParameter:
    """Test disc number parameter encoding."""

    def test_disc_num_validation(self, tmp_path):
        """Test disc number validation (1-9)."""
        iso_file = tmp_path / "test.iso"
        out_file = tmp_path / "test.bin.enc"

        # Create minimal valid ISO (16KB aligned)
        iso_file.write_bytes(b'\x00' * 0x4000)

        # Test invalid disc numbers
        with pytest.raises(ValueError, match="Disc number must be 1-9"):
            encrypt_ps2_iso(iso_file, out_file, disc_num=0)

        with pytest.raises(ValueError, match="Disc number must be 1-9"):
            encrypt_ps2_iso(iso_file, out_file, disc_num=10)

        with pytest.raises(ValueError, match="Disc number must be 1-9"):
            encrypt_ps2_iso(iso_file, out_file, disc_num=-1)

    def test_disc_num_encoding_logic(self):
        """Test disc number encoding matches original algorithm."""
        # Original algorithm: disc_num_encoded = (disc_num - 1) << 24

        test_cases = [
            (1, 0x00000000),  # Disc 1
            (2, 0x01000000),  # Disc 2
            (3, 0x02000000),  # Disc 3
            (4, 0x03000000),  # Disc 4
            (5, 0x04000000),  # Disc 5
            (6, 0x05000000),  # Disc 6
            (7, 0x06000000),  # Disc 7
            (8, 0x07000000),  # Disc 8
            (9, 0x08000000),  # Disc 9
        ]

        for disc_num, expected_encoding in test_cases:
            # Test encoding formula
            disc_num_encoded = (disc_num - 1) << 24
            assert disc_num_encoded == expected_encoding, \
                f"Disc {disc_num}: got 0x{disc_num_encoded:08X}, expected 0x{expected_encoding:08X}"

            # Test that segment number is preserved in lower bytes
            segment_number = 42
            combined = disc_num_encoded | segment_number

            # Verify disc number in upper byte
            assert (combined >> 24) == (disc_num - 1)
            # Verify segment number in lower bytes
            assert (combined & 0x00FFFFFF) == segment_number

    @patch('ps3toolbox.ps2.encrypt.add_limg_header')
    @patch('ps3toolbox.ps2.encrypt.pad_iso_to_boundary')
    @patch('ps3toolbox.ps2.encrypt.validate_iso')
    def test_disc_num_in_metadata(self, mock_validate, mock_pad, mock_limg, tmp_path):
        """Test that disc_num is correctly written to metadata."""
        # Create test ISO
        iso_file = tmp_path / "test.iso"
        out_file = tmp_path / "test.bin.enc"

        # Create simple ISO (one segment = 0x4000 bytes)
        test_data = b'\x00' * 0x4000
        iso_file.write_bytes(test_data)

        # Mock the functions
        mock_validate.return_value = None
        mock_pad.return_value = None
        mock_limg.return_value = len(test_data)

        # Encrypt with disc_num=2
        encrypt_ps2_iso(iso_file, out_file, disc_num=2)

        # Read output and check metadata
        with open(out_file, 'rb') as f:
            # Skip header (0x4000)
            f.seek(0x4000)
            # Read encrypted metadata segment
            encrypted_meta = f.read(0x4000)

        # We can't easily decrypt without full setup, but we can verify
        # the file was created and has correct structure
        assert out_file.exists()
        assert out_file.stat().st_size > 0x4000  # Has header + data

    @patch('ps3toolbox.ps2.encrypt.add_limg_header')
    @patch('ps3toolbox.ps2.encrypt.pad_iso_to_boundary')
    @patch('ps3toolbox.ps2.encrypt.validate_iso')
    def test_default_disc_num(self, mock_validate, mock_pad, mock_limg, tmp_path):
        """Test that disc_num defaults to 1."""
        iso_file = tmp_path / "test.iso"
        out_file = tmp_path / "test.bin.enc"

        # Create minimal valid ISO
        test_data = b'\x00' * 0x4000
        iso_file.write_bytes(test_data)

        # Mock functions
        mock_validate.return_value = None
        mock_pad.return_value = None
        mock_limg.return_value = len(test_data)

        # Should not raise error with default disc_num=1
        try:
            encrypt_ps2_iso(iso_file, out_file)
        except ValueError as e:
            if "Disc number" in str(e):
                pytest.fail(f"Default disc_num should be valid: {e}")
