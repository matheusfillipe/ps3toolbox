"""LIMG (Last Image) header handling."""

import struct
from pathlib import Path
from ps3toolbox.core.iso import is_dvd_iso


def has_limg_header(iso_path: Path) -> bool:
    """Check if ISO already has valid LIMG header."""
    try:
        with open(iso_path, 'rb') as f:
            f.seek(-0x4000, 2)
            magic = f.read(4)
            return magic == b'LIMG'
    except (IOError, OSError):
        return False


def build_limg_header(iso_path: Path, iso_size: int) -> bytes:
    """Build LIMG header sector (0x4000 bytes)."""
    header = bytearray(0x4000)
    header[0:4] = b'LIMG'

    is_dvd = is_dvd_iso(iso_path)
    block_size = 0x800 if is_dvd else 0x930

    with open(iso_path, 'rb') as f:
        if is_dvd:
            f.seek(0x8000 + 0x54)
        else:
            f.seek(0x9318 + 0x54)
        num_sectors_bytes = f.read(4)
        num_sectors = struct.unpack('<I', num_sectors_bytes)[0]

    struct.pack_into('>I', header, 0x04, 0x01 if is_dvd else 0x02)
    struct.pack_into('>I', header, 0x08, num_sectors)

    if is_dvd:
        struct.pack_into('>I', header, 0x0C, 0x00000800)
    else:
        struct.pack_into('>I', header, 0x0C, 0x00000930)

    return bytes(header)


def add_limg_header(iso_path: Path) -> int:
    """Add LIMG header to ISO if missing, return final size."""
    if has_limg_header(iso_path):
        return iso_path.stat().st_size

    original_size = iso_path.stat().st_size
    limg_header = build_limg_header(iso_path, original_size)

    with open(iso_path, 'ab') as f:
        f.write(limg_header)

    return iso_path.stat().st_size
