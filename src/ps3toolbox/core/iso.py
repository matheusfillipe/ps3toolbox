"""ISO validation and preparation utilities."""

from pathlib import Path
from ps3toolbox.utils.errors import InvalidISOError


def validate_iso(iso_path: Path) -> bool:
    """Validate PS2 ISO9660 format by checking signature."""
    with open(iso_path, 'rb') as f:
        f.seek(0x8000)
        dvd_sig = f.read(6)

        if dvd_sig == b'\x01CD001':
            return True

        f.seek(0x9318)
        cd_sig = f.read(6)

        if cd_sig == b'\x01CD001':
            return True

    raise InvalidISOError(f"Invalid ISO9660 signature in {iso_path}")


def get_iso_size(iso_path: Path) -> int:
    """Get ISO file size in bytes."""
    return iso_path.stat().st_size


def is_dvd_iso(iso_path: Path) -> bool:
    """Check if ISO is DVD format (>700MB threshold)."""
    return get_iso_size(iso_path) > 0x2BC00000


def pad_iso_to_boundary(iso_path: Path, boundary: int = 0x4000) -> int:
    """Pad ISO file to specified boundary, return padding added."""
    current_size = get_iso_size(iso_path)
    padding_needed = (boundary - (current_size % boundary)) % boundary

    if padding_needed > 0:
        with open(iso_path, 'ab') as f:
            f.write(b'\x00' * padding_needed)

    return padding_needed
