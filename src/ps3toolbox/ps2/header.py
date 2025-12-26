"""PS2 Classics header operations."""

import struct
from typing import TypedDict

from ps3toolbox.core.crypto import calculate_omac
from ps3toolbox.core.keys import NPD_KEK
from ps3toolbox.core.keys import NPD_OMAC_KEY2
from ps3toolbox.core.keys import NPD_OMAC_KEY3
from ps3toolbox.core.keys import SEGMENT_SIZE


class PS2Metadata(TypedDict):
    """PS2 Classics metadata structure."""

    magic: str
    version_major: int
    version_minor: int
    npd_type: int
    type: int
    content_id: str
    segment_size: int
    iso_size: int


def build_ps2_header(content_id: str, filename: str, iso_size: int, npd_type: int = 2) -> bytes:
    """Build PS2 Classics header (0x4000 bytes)."""
    header = bytearray(SEGMENT_SIZE)

    header[0x00:0x04] = b"PS2\x00"
    struct.pack_into(">H", header, 0x04, 0x0001)
    struct.pack_into(">H", header, 0x06, 0x0001)
    struct.pack_into(">I", header, 0x08, npd_type)
    struct.pack_into(">I", header, 0x0C, 0x0001)

    cid_bytes = content_id.encode("ascii")[:0x30]
    header[0x10 : 0x10 + len(cid_bytes)] = cid_bytes

    struct.pack_into(">I", header, 0x84, SEGMENT_SIZE)
    struct.pack_into(">Q", header, 0x88, iso_size)

    header[0x40:0x50] = b"bucanero.com.ar\x00"

    npd_omac_key = bytes(NPD_KEK[i] ^ NPD_OMAC_KEY2[i] for i in range(16))

    buf = header[0x10:0x40] + filename.encode("ascii")
    header[0x50:0x60] = calculate_omac(buf, NPD_OMAC_KEY3)
    header[0x60:0x70] = calculate_omac(bytes(header[0x00:0x60]), npd_omac_key)

    return bytes(header)


def parse_ps2_header(header: bytes) -> PS2Metadata:
    """Parse PS2 header and extract metadata."""
    if header[0:4] != b"PS2\x00":
        raise ValueError("Invalid PS2 header magic")

    return {
        "magic": header[0:4].decode("ascii", errors="ignore"),
        "version_major": struct.unpack(">H", header[0x04:0x06])[0],
        "version_minor": struct.unpack(">H", header[0x06:0x08])[0],
        "npd_type": struct.unpack(">I", header[0x08:0x0C])[0],
        "type": struct.unpack(">I", header[0x0C:0x10])[0],
        "content_id": header[0x10:0x40].decode("ascii", errors="ignore").rstrip("\x00"),
        "segment_size": struct.unpack(">I", header[0x84:0x88])[0],
        "iso_size": struct.unpack(">Q", header[0x88:0x90])[0],
    }


def verify_header(header: bytes) -> bool:
    """Verify header has valid magic and structure."""
    return (
        len(header) >= 0x90 and header[0:4] == b"PS2\x00" and struct.unpack(">I", header[0x84:0x88])[0] == SEGMENT_SIZE
    )
