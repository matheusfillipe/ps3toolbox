"""Disc number detection from filenames."""

import re


def detect_disc_number(filename: str) -> int:
    """
    Detect disc number from filename.

    Supports patterns like:
    - "Game (Disc 1).iso"
    - "Game [Disc 2].iso"
    - "Game - Disc 3.iso"
    - "Game_Disc1.iso"
    - "Game disc1.iso"
    - "Game CD1.iso"
    - "Game D1.iso"
    - "Game (CD 2).iso"
    - "Game_d2.iso"

    Returns:
        Disc number (1-9), defaults to 1 if not detected
    """
    # Patterns to match disc numbers
    patterns = [
        r'disc[\s_-]*(\d)',  # disc 1, disc_1, disc-1, disc1
        r'disk[\s_-]*(\d)',  # disk 1, disk_1, disk-1, disk1
        r'cd[\s_-]*(\d)',    # cd 1, cd_1, cd-1, cd1
        r'd[\s_-]*(\d)',     # d 1, d_1, d-1, d1
        r'\(disc[\s_]*(\d)\)',  # (disc 1), (disc1)
        r'\[disc[\s_]*(\d)\]',  # [disc 1], [disc1]
        r'\(cd[\s_]*(\d)\)',    # (cd 1), (cd1)
        r'\[cd[\s_]*(\d)\]',    # [cd 1], [cd1]
        r'\(d[\s_]*(\d)\)',     # (d 1), (d1)
        r'\[d[\s_]*(\d)\]',     # [d 1], [d1]
    ]

    filename_lower = filename.lower()

    for pattern in patterns:
        match = re.search(pattern, filename_lower)
        if match:
            disc_num = int(match.group(1))
            if 1 <= disc_num <= 9:
                return disc_num

    # Default to disc 1
    return 1
