"""Unit tests for disc number detection."""

import pytest
from ps3toolbox.utils.disc_detect import detect_disc_number


class TestDiscNumberDetection:
    """Test automatic disc number detection from filenames."""

    def test_disc_patterns(self):
        """Test various disc patterns."""
        test_cases = [
            # Standard patterns
            ("Final Fantasy X (Disc 1).iso", 1),
            ("Final Fantasy X (Disc 2).iso", 2),
            ("Xenosaga [Disc 1].iso", 1),
            ("Xenosaga [Disc 2].iso", 2),
            ("Game - Disc 3.iso", 3),
            ("Game_Disc1.iso", 1),
            ("Game disc2.iso", 2),

            # CD patterns
            ("Game (CD 1).iso", 1),
            ("Game [CD 2].iso", 2),
            ("Game CD1.iso", 1),
            ("Game_cd2.iso", 2),

            # Disk patterns
            ("Game (Disk 1).iso", 1),
            ("Game [Disk 2].iso", 2),
            ("Game disk1.iso", 1),

            # D patterns
            ("Game (D 1).iso", 1),
            ("Game [D 2].iso", 2),
            ("Game D1.iso", 1),
            ("Game_d2.iso", 2),

            # Case insensitive
            ("GAME (DISC 1).ISO", 1),
            ("game [disc 2].iso", 2),

            # With extra info
            ("Final Fantasy X (USA) (Disc 1).iso", 1),
            ("Xenosaga Episode I [NTSC] [Disc 2].iso", 2),

            # No disc number (defaults to 1)
            ("Gran Turismo 4.iso", 1),
            ("Game.iso", 1),
            ("Random Name (USA).iso", 1),
        ]

        for filename, expected_disc in test_cases:
            detected = detect_disc_number(filename)
            assert detected == expected_disc, \
                f"Failed for '{filename}': expected {expected_disc}, got {detected}"

    def test_multi_disc_series(self):
        """Test multi-disc game series."""
        test_cases = [
            ("Xenosaga Episode I (Disc 1).iso", 1),
            ("Xenosaga Episode I (Disc 2).iso", 2),
            ("Xenosaga Episode II (Disc 1).iso", 1),
            ("Xenosaga Episode III (Disc 1).iso", 1),
        ]

        for filename, expected_disc in test_cases:
            assert detect_disc_number(filename) == expected_disc

    def test_edge_cases(self):
        """Test edge cases."""
        # High disc numbers
        assert detect_disc_number("Game (Disc 9).iso") == 9

        # Invalid disc numbers (>9) should default to 1
        assert detect_disc_number("Game (Disc 10).iso") == 1
        assert detect_disc_number("Game (Disc 0).iso") == 1

        # No extension
        assert detect_disc_number("Game (Disc 2)") == 2

        # Multiple disc references (should match first)
        assert detect_disc_number("Game Disc 1 of 2.iso") == 1

    def test_real_world_filenames(self):
        """Test real-world PS2 game filenames."""
        test_cases = [
            ("Final Fantasy X (USA).iso", 1),
            ("Gran Turismo 4 (SLUS-21001).iso", 1),
            ("Metal Gear Solid 3 - Snake Eater (USA) (Disc 1).iso", 1),
            ("Xenosaga Episode I - Der Wille zur Macht (USA) (Disc 2).iso", 2),
            ("Star Ocean - Till the End of Time (USA) (Disc 1).iso", 1),
            ("Star Ocean - Till the End of Time (USA) (Disc 2).iso", 2),
        ]

        for filename, expected_disc in test_cases:
            assert detect_disc_number(filename) == expected_disc
